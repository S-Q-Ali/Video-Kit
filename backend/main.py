import re
from flask import Flask, request, jsonify, render_template, send_file, Response, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import subprocess
import os
import json
import uuid
import zipfile
import threading
import time
import shutil
import glob as glob_module

from youtube_api import youtube_bp
from api_v1 import api as api_v1_bp

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB

# ── CORS ───────────────────────────────────────────────────────────────────────
# Allow the Vercel-hosted frontend (and local dev frontends) to call this API.
# In production set ALLOWED_ORIGINS to a comma-separated list of origins.
_default_origins = [
    'http://localhost:5000',
    'http://127.0.0.1:5000',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
]
_env_origins = [o.strip() for o in os.environ.get('ALLOWED_ORIGINS', '').split(',') if o.strip()]
allowed_origins = _env_origins or _default_origins
CORS(
    app,
    resources={r'/*': {'origins': allowed_origins}},
    supports_credentials=False,
    max_age=86400,
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
# Applies per client IP. /api/* routes have stricter limits; legacy routes
# (used by the existing analyzer UI) are exempted to avoid breaking behavior.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=['200 per hour'],
    storage_uri='memory://',
)
limiter.limit('30 per minute')(youtube_bp)

# Register blueprints
app.register_blueprint(youtube_bp)               # /api/video/*
app.register_blueprint(api_v1_bp)                # /api/v1/*

UPLOAD_FOLDER = '/tmp'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm'}
MAX_FRAMES = 3000


def timestamp():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def cleanup_old_files(max_age_secs=3600):
    try:
        now = time.time()
        for filepath in glob_module.glob('/tmp/vidlab_*'):
            try:
                age = now - os.path.getmtime(filepath)
                if age > max_age_secs:
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                        print(f'[{timestamp()}] Cleaned file: {filepath}')
                    elif os.path.isdir(filepath):
                        shutil.rmtree(filepath, ignore_errors=True)
                        print(f'[{timestamp()}] Cleaned dir: {filepath}')
            except Exception as e:
                print(f'[{timestamp()}] Cleanup error for {filepath}: {e}')
    except Exception as e:
        print(f'[{timestamp()}] Cleanup scan error: {e}')


def cleanup_old_files_background():
    cleanup_old_files()
    t = threading.Timer(1800, cleanup_old_files_background)
    t.daemon = True
    t.start()


def nuke_frame_dirs():
    for path in glob_module.glob('/tmp/vidlab_*_frames'):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                print(f'[{timestamp()}] Nuked frame dir: {path}')
        except Exception as e:
            print(f'[{timestamp()}] nuke_frame_dirs error {path}: {e}')


def pre_process_cleanup():
    nuke_frame_dirs()
    cleanup_old_files(max_age_secs=1800)


def remove_dir(path):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        print(f'[{timestamp()}] remove_dir error {path}: {e}')


# ── FFmpeg progress helpers ────────────────────────────────────────────────────

def _parse_duration(line):
    m = re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', line)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return None


def _parse_time(line):
    m = re.search(r'\btime=(\d+):(\d+):([\d.]+)', line)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return None


def _sse(data):
    """Format a Server-Sent Event frame."""
    return f"data: {json.dumps(data)}\n\n"


def _run_ffmpeg_progress(cmd, pct_start, pct_end, step, timeout=300):
    """
    Run an FFmpeg command and yield SSE-formatted progress events.
    Yields _sse({percent, step}) during processing.
    Finally yields (returncode, stderr_str).
    Caller must iterate fully to get returncode.
    """
    total_dur = None
    stderr_acc = []
    last_pct = pct_start

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        return -2, 'FFmpeg not installed — add ffmpeg to system packages'

    start_time = time.time()

    def read_stderr():
        nonlocal total_dur, last_pct
        for line in proc.stderr:
            stderr_acc.append(line)
            if time.time() - start_time > timeout:
                proc.kill()
                return 'timeout'
            if total_dur is None:
                d = _parse_duration(line)
                if d and d > 0:
                    total_dur = d
            t = _parse_time(line)
            if t is not None and total_dur and total_dur > 0:
                frac = min(t / total_dur, 1.0)
                pct = int(pct_start + frac * (pct_end - pct_start))
                if pct > last_pct:
                    last_pct = pct
        return None

    result = read_stderr()
    proc.wait()

    if result == 'timeout':
        return -1, 'Processing timed out. Try a shorter or smaller video.'

    return proc.returncode, ''.join(stderr_acc)


# ── Quality / detection helpers ────────────────────────────────────────────────

def compute_quality_score(height, fps, bitrate_kbps, codec):
    score = 0
    if height >= 2160: score += 40
    elif height >= 1080: score += 30
    elif height >= 720: score += 20
    elif height >= 480: score += 10
    if fps >= 60: score += 20
    elif fps >= 30: score += 15
    elif fps >= 24: score += 10
    if bitrate_kbps >= 8000: score += 20
    elif bitrate_kbps >= 4000: score += 15
    elif bitrate_kbps >= 1000: score += 10
    cl = codec.lower() if codec else ''
    if cl in ['hevc', 'h265', 'av1', 'vp9']: score += 20
    elif cl in ['h264', 'avc']: score += 15
    else: score += 5
    return min(score, 100)


def quality_label(score):
    if score < 40: return 'Poor'
    if score < 60: return 'Fair'
    if score < 80: return 'Good'
    return 'Excellent'


def detected_type(width, height, fps, codec, bitrate_kbps):
    cl = codec.lower() if codec else ''
    ratio = width / height if height > 0 else 0
    if ratio > 1.7 and fps >= 23: return 'Cinematic / Widescreen'
    if height > width: return 'Vertical / Mobile Video'
    if fps >= 50: return 'High Frame Rate Video'
    if cl in ['hevc', 'av1']: return 'High Efficiency Video'
    if bitrate_kbps < 500: return 'Compressed / Web Video'
    return 'Standard Video'


def get_file_path(file_id):
    for ext in ALLOWED_EXTENSIONS:
        path = f'/tmp/vidlab_{file_id}.{ext}'
        if os.path.exists(path):
            return path
    return None


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(f.filename):
        return jsonify({'error': 'File type not allowed. Use mp4, mov, avi, mkv, or webm.'}), 400

    ext = f.filename.rsplit('.', 1)[1].lower()
    file_id = str(uuid.uuid4())
    filename = f'vidlab_{file_id}.{ext}'
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    try:
        f.save(filepath)
        file_size = os.path.getsize(filepath)
        if file_size > 200 * 1024 * 1024:
            os.remove(filepath)
            return jsonify({'error': 'File too large. Max 200MB.'}), 413
        print(f'[{timestamp()}] Uploaded: {filename} ({file_size / 1024 / 1024:.2f} MB)')
        return jsonify({'file_id': file_id, 'filename': f.filename, 'size_mb': round(file_size / 1024 / 1024, 2)})
    except OSError as e:
        if 'No space left' in str(e) or 'Disk quota' in str(e):
            return jsonify({'error': 'Disk quota exceeded on server. Please try again shortly.'}), 500
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        print(f'[{timestamp()}] Upload error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/analyze', methods=['POST'])
def analyze():
    """SSE-streaming analysis route."""
    data = request.get_json()
    if not data or 'file_id' not in data:
        return jsonify({'error': 'Missing file_id'}), 400

    file_id = data['file_id']
    filepath = get_file_path(file_id)
    if not filepath:
        return jsonify({'error': 'File not found'}), 404

    def generate():
        yield _sse({'percent': 5, 'step': 'Reading video metadata...'})

        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                 '-show_streams', '-show_format', filepath],
                capture_output=True, text=True, timeout=60
            )
        except FileNotFoundError:
            yield _sse({'error': 'FFmpeg not installed — add ffmpeg to system packages'})
            return
        except subprocess.TimeoutExpired:
            yield _sse({'error': 'Analysis timed out'})
            return

        yield _sse({'percent': 60, 'step': 'Processing metadata...'})

        if result.returncode != 0:
            yield _sse({'error': f'ffprobe failed: {result.stderr[-300:]}'})
            return

        try:
            probe = json.loads(result.stdout)
        except Exception as e:
            yield _sse({'error': f'Failed to parse ffprobe output: {e}'})
            return

        fmt = probe.get('format', {})
        streams = probe.get('streams', [])
        video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
        audio_stream = next((s for s in streams if s.get('codec_type') == 'audio'), None)

        if not video_stream:
            yield _sse({'error': 'No video stream found'})
            return

        fps_raw = video_stream.get('r_frame_rate', '0/1')
        try:
            num, den = fps_raw.split('/')
            fps = round(float(num) / float(den), 3) if float(den) != 0 else 0
        except Exception:
            fps = 0

        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        duration_raw = float(video_stream.get('duration', fmt.get('duration', 0)))
        duration_seconds = round(duration_raw, 2)
        total_frames = round(fps * duration_seconds)
        codec = video_stream.get('codec_name', 'unknown')
        codec_long = video_stream.get('codec_long_name', 'unknown')
        pixel_format = video_stream.get('pix_fmt', 'unknown')
        color_space = video_stream.get('color_space', 'unknown') or 'unknown'
        color_range = video_stream.get('color_range', 'unknown') or 'unknown'
        color_primaries = video_stream.get('color_primaries', 'unknown') or 'unknown'

        try:
            bitrate_kbps = int(int(fmt.get('bit_rate', 0)) / 1000)
        except Exception:
            bitrate_kbps = 0

        try:
            video_bitrate_kbps = int(int(video_stream.get('bit_rate', 0)) / 1000) if video_stream.get('bit_rate') else None
        except Exception:
            video_bitrate_kbps = None

        file_size_bytes = int(fmt.get('size', os.path.getsize(filepath)))
        file_size_mb = round(file_size_bytes / 1024 / 1024, 2)
        aspect_ratio = video_stream.get('display_aspect_ratio', f'{width}:{height}')
        profile = video_stream.get('profile', 'unknown')
        level = video_stream.get('level', 'unknown')
        nb_frames = video_stream.get('nb_frames', None)

        has_audio = audio_stream is not None
        if has_audio:
            audio_codec = audio_stream.get('codec_name', 'none')
            audio_codec_long = audio_stream.get('codec_long_name', 'none')
            audio_sample_rate = audio_stream.get('sample_rate', 'unknown')
            audio_channels = int(audio_stream.get('channels', 0))
            audio_channel_layout = audio_stream.get('channel_layout', 'unknown')
            try:
                audio_bitrate_kbps = int(int(audio_stream.get('bit_rate', 0)) / 1000) if audio_stream.get('bit_rate') else None
            except Exception:
                audio_bitrate_kbps = None
        else:
            audio_codec = audio_codec_long = audio_sample_rate = 'none'
            audio_channels = 0
            audio_channel_layout = 'none'
            audio_bitrate_kbps = None

        format_name = fmt.get('format_name', 'unknown')
        format_long = fmt.get('format_long_name', 'unknown')
        nb_streams = int(fmt.get('nb_streams', 0))
        q_score = compute_quality_score(height, fps, bitrate_kbps, codec)

        yield _sse({'percent': 100, 'done': True, 'result': {
            'fps': fps, 'resolution': f'{width}x{height}', 'width': width, 'height': height,
            'duration_seconds': duration_seconds, 'total_frames': total_frames,
            'codec': codec, 'codec_long': codec_long, 'pixel_format': pixel_format,
            'color_space': color_space, 'color_range': color_range, 'color_primaries': color_primaries,
            'bitrate_kbps': bitrate_kbps, 'video_bitrate_kbps': video_bitrate_kbps,
            'file_size_mb': file_size_mb, 'aspect_ratio': aspect_ratio, 'profile': profile,
            'level': level, 'nb_frames': nb_frames,
            'has_audio': has_audio, 'audio_codec': audio_codec, 'audio_codec_long': audio_codec_long,
            'audio_sample_rate': audio_sample_rate, 'audio_channels': audio_channels,
            'audio_channel_layout': audio_channel_layout, 'audio_bitrate_kbps': audio_bitrate_kbps,
            'format_name': format_name, 'format_long': format_long, 'nb_streams': nb_streams,
            'quality_score': q_score, 'quality_label': quality_label(q_score),
            'detected_type': detected_type(width, height, fps, codec, bitrate_kbps),
        }})

    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/duplicate', methods=['POST'])
def duplicate():
    """SSE-streaming duplicate route."""
    data = request.get_json()
    if not data or 'file_id' not in data:
        return jsonify({'error': 'Missing file_id'}), 400

    file_id = data['file_id']
    fps_extract = data.get('fps_extract', 1)
    filepath = get_file_path(file_id)
    if not filepath:
        return jsonify({'error': 'File not found'}), 404

    out_id = str(uuid.uuid4())
    clean_path = f'/tmp/vidlab_{out_id}_clean.mp4'
    frames_dir = f'/tmp/vidlab_{out_id}_frames'
    frames_zip = f'/tmp/vidlab_{out_id}_frames.zip'

    def generate():
        pre_process_cleanup()
        os.makedirs(frames_dir, exist_ok=True)

        # ── Phase 1: Clean copy (0-40%) ──────────────────────────────────────
        yield _sse({'percent': 2, 'step': 'Stripping metadata...'})

        cmd_clean = [
            'ffmpeg', '-y', '-i', filepath,
            '-map_metadata', '-1', '-map_chapters', '-1',
            '-c:v', 'libx264', '-crf', '18', '-preset', 'fast',
            '-c:a', 'aac', '-movflags', '+faststart',
            clean_path
        ]

        total_dur = None
        stderr_acc = []
        timed_out = False

        try:
            proc = subprocess.Popen(cmd_clean, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, text=True, bufsize=1)
        except FileNotFoundError:
            remove_dir(frames_dir)
            yield _sse({'error': 'FFmpeg not installed — add ffmpeg to system packages'})
            return

        start = time.time()
        for line in proc.stderr:
            stderr_acc.append(line)
            if time.time() - start > 300:
                proc.kill()
                timed_out = True
                break
            if total_dur is None:
                d = _parse_duration(line)
                if d and d > 0:
                    total_dur = d
            t = _parse_time(line)
            if t is not None and total_dur:
                pct = int(2 + min(t / total_dur, 1.0) * 38)
                yield _sse({'percent': pct, 'step': 'Stripping metadata...'})
        proc.wait()

        if timed_out:
            remove_dir(frames_dir)
            yield _sse({'error': 'Processing timed out. Try a shorter or smaller video.'})
            return

        if proc.returncode != 0:
            remove_dir(frames_dir)
            stderr = ''.join(stderr_acc)
            if 'No space left' in stderr or 'Disk quota' in stderr:
                yield _sse({'error': 'Disk quota exceeded. Try a smaller video.'})
            else:
                yield _sse({'error': f'Clean copy failed: {stderr[-300:]}'})
            return

        # ── Phase 2: Frame extraction (40-90%) ───────────────────────────────
        yield _sse({'percent': 40, 'step': 'Extracting frames...'})

        every_frame = (fps_extract == 0)
        if every_frame:
            cmd_frames = ['ffmpeg', '-y', '-i', filepath, '-vsync', '0',
                          '-q:v', '5', f'{frames_dir}/frame_%04d.jpg']
        else:
            cmd_frames = ['ffmpeg', '-y', '-i', filepath,
                          '-vf', f'fps={float(fps_extract)}',
                          '-q:v', '5', f'{frames_dir}/frame_%04d.jpg']

        total_dur2 = None
        stderr_acc2 = []
        timed_out2 = False

        try:
            proc2 = subprocess.Popen(cmd_frames, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE, text=True, bufsize=1)
        except FileNotFoundError:
            remove_dir(frames_dir)
            yield _sse({'error': 'FFmpeg not installed'})
            return

        start2 = time.time()
        for line in proc2.stderr:
            stderr_acc2.append(line)
            if time.time() - start2 > 300:
                proc2.kill()
                timed_out2 = True
                break
            if total_dur2 is None:
                d = _parse_duration(line)
                if d and d > 0:
                    total_dur2 = d
            t = _parse_time(line)
            if t is not None and total_dur2:
                pct = int(40 + min(t / total_dur2, 1.0) * 50)
                yield _sse({'percent': pct, 'step': 'Extracting frames...'})
        proc2.wait()

        if timed_out2:
            remove_dir(frames_dir)
            yield _sse({'error': 'Frame extraction timed out. Try lower FPS or a shorter video.'})
            return

        if proc2.returncode != 0:
            remove_dir(frames_dir)
            stderr = ''.join(stderr_acc2)
            if 'No space left' in stderr or 'Disk quota' in stderr:
                yield _sse({'error': 'Disk quota exceeded. Try lower FPS or a smaller video.'})
            else:
                yield _sse({'error': f'Frame extraction failed: {stderr[-300:]}'})
            return

        # ── Phase 3: ZIP frames (90-100%) ────────────────────────────────────
        yield _sse({'percent': 90, 'step': 'Creating ZIP archive...'})

        jpg_files = sorted(glob_module.glob(f'{frames_dir}/frame_*.jpg'))
        frame_count = len(jpg_files)

        if frame_count > MAX_FRAMES:
            for excess in jpg_files[MAX_FRAMES:]:
                try: os.remove(excess)
                except Exception: pass
            jpg_files = jpg_files[:MAX_FRAMES]
            frame_count = MAX_FRAMES

        preview_frames = [os.path.basename(f) for f in jpg_files[:6]]

        try:
            with zipfile.ZipFile(frames_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                for jpg in jpg_files:
                    zf.write(jpg, os.path.basename(jpg))
        except OSError as e:
            remove_dir(frames_dir)
            if 'No space left' in str(e) or 'Disk quota' in str(e):
                yield _sse({'error': 'Disk quota exceeded while creating ZIP.'})
            else:
                yield _sse({'error': str(e)})
            return

        remove_dir(frames_dir)

        clean_size_mb = round(os.path.getsize(clean_path) / 1024 / 1024, 2)
        original_size_mb = round(os.path.getsize(filepath) / 1024 / 1024, 2)

        print(f'[{timestamp()}] Duplicate done: {frame_count} frames, clean={clean_size_mb}MB')
        yield _sse({'percent': 100, 'done': True, 'result': {
            'clean_video_id': f'{out_id}_clean',
            'frames_zip_id': f'{out_id}_frames',
            'frame_count': frame_count,
            'preview_frames': preview_frames,
            'clean_size_mb': clean_size_mb,
            'original_size_mb': original_size_mb,
            'frames_dir_id': out_id,
        }})

    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/modify', methods=['POST'])
def modify():
    """SSE-streaming modify route."""
    data = request.get_json()
    if not data or 'file_id' not in data:
        return jsonify({'error': 'Missing file_id'}), 400

    file_id = data['file_id']
    operations = data.get('operations', {})
    filepath = get_file_path(file_id)
    if not filepath:
        return jsonify({'error': 'File not found'}), 404

    out_id = str(uuid.uuid4())
    extract_audio = operations.get('extract_audio', False)
    output_ext = 'mp3' if extract_audio else 'mp4'
    output_path = f'/tmp/vidlab_{out_id}_modified.{output_ext}'

    def generate():
        pre_process_cleanup()
        yield _sse({'percent': 2, 'step': 'Building FFmpeg command...'})

        cmd = ['ffmpeg', '-y']

        trim = operations.get('trim')
        if trim:
            start = trim.get('start', 0)
            end = trim.get('end')
            cmd += ['-ss', str(start)]
            if end is not None:
                cmd += ['-to', str(end)]

        cmd += ['-i', filepath]

        if extract_audio:
            cmd += ['-vn', '-acodec', 'libmp3lame', '-q:a', '2', output_path]
        else:
            vf_filters = []
            af_filters = []

            resize = operations.get('resize')
            if resize:
                w = resize.get('width', -1)
                h = resize.get('height', -1)
                vf_filters.append(f'scale={w}:{h}')

            fps_op = operations.get('fps')
            if fps_op:
                vf_filters.append(f'fps={fps_op["value"]}')

            rotate = operations.get('rotate')
            if rotate:
                deg = rotate.get('degrees', 0)
                if deg == 90:
                    vf_filters.append('transpose=1')
                elif deg == -90 or deg == 270:
                    vf_filters.append('transpose=2')
                elif deg == 180:
                    vf_filters.append('transpose=2,transpose=2')

            speed = operations.get('speed')
            if speed:
                speed_val = float(speed.get('value', 1.0))
                pts_val = round(1.0 / speed_val, 6)
                vf_filters.append(f'setpts={pts_val}*PTS')
                if speed_val > 2.0:
                    remaining = speed_val
                    while remaining > 2.0:
                        af_filters.append('atempo=2.0')
                        remaining /= 2.0
                    af_filters.append(f'atempo={remaining:.4f}')
                elif speed_val < 0.5:
                    remaining = speed_val
                    while remaining < 0.5:
                        af_filters.append('atempo=0.5')
                        remaining *= 2.0
                    af_filters.append(f'atempo={remaining:.4f}')
                else:
                    af_filters.append(f'atempo={speed_val:.4f}')

            mute = operations.get('mute', False)

            if vf_filters:
                cmd += ['-vf', ','.join(vf_filters)]
            else:
                cmd += ['-c:v', 'copy']

            if mute:
                cmd += ['-an']
            elif af_filters:
                cmd += ['-af', ','.join(af_filters)]
            else:
                cmd += ['-c:a', 'copy' if not vf_filters else 'aac']

            cmd.append(output_path)

        # ── Run FFmpeg with real progress ─────────────────────────────────────
        yield _sse({'percent': 5, 'step': 'Processing video...'})

        total_dur = None
        stderr_acc = []
        timed_out = False

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, text=True, bufsize=1)
        except FileNotFoundError:
            yield _sse({'error': 'FFmpeg not installed — add ffmpeg to system packages'})
            return

        start = time.time()
        for line in proc.stderr:
            stderr_acc.append(line)
            if time.time() - start > 600:
                proc.kill()
                timed_out = True
                break
            if total_dur is None:
                d = _parse_duration(line)
                if d and d > 0:
                    total_dur = d
            t = _parse_time(line)
            if t is not None and total_dur:
                pct = int(5 + min(t / total_dur, 1.0) * 90)
                yield _sse({'percent': pct, 'step': 'Processing video...'})
        proc.wait()

        if timed_out:
            if os.path.exists(output_path):
                os.remove(output_path)
            yield _sse({'error': 'Processing timed out. Try a shorter video or fewer operations.'})
            return

        if proc.returncode != 0:
            if os.path.exists(output_path):
                os.remove(output_path)
            stderr = ''.join(stderr_acc)
            if 'No space left' in stderr or 'Disk quota' in stderr:
                yield _sse({'error': 'Disk quota exceeded. Try trimming the video first or use a smaller file.'})
            else:
                print(f'[{timestamp()}] Modify error: {stderr}')
                yield _sse({'error': f'FFmpeg failed: {stderr[-300:]}'})
            return

        yield _sse({'percent': 97, 'step': 'Finalizing...'})

        probe_result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', output_path],
            capture_output=True, text=True, timeout=30
        )
        size_mb = round(os.path.getsize(output_path) / 1024 / 1024, 2)
        duration_out = 0
        if probe_result.returncode == 0:
            probe_data = json.loads(probe_result.stdout)
            duration_out = round(float(probe_data.get('format', {}).get('duration', 0)), 2)

        yield _sse({'percent': 100, 'done': True, 'result': {
            'output_id': f'{out_id}_modified',
            'output_type': 'audio' if extract_audio else 'video',
            'output_ext': output_ext,
            'size_mb': size_mb,
            'duration_seconds': duration_out,
        }})

    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/download/<file_id>')
def download(file_id):
    try:
        if file_id.endswith('_clean'):
            base = file_id[:-6]
            path = f'/tmp/vidlab_{base}_clean.mp4'
            filename = 'clean_video.mp4'
            mimetype = 'video/mp4'
        elif file_id.endswith('_frames'):
            base = file_id[:-7]
            path = f'/tmp/vidlab_{base}_frames.zip'
            filename = 'frames.zip'
            mimetype = 'application/zip'
        elif file_id.endswith('_modified'):
            base = file_id[:-9]
            mp4_path = f'/tmp/vidlab_{base}_modified.mp4'
            mp3_path = f'/tmp/vidlab_{base}_modified.mp3'
            if os.path.exists(mp4_path):
                path = mp4_path
                filename = 'modified_video.mp4'
                mimetype = 'video/mp4'
            elif os.path.exists(mp3_path):
                path = mp3_path
                filename = 'extracted_audio.mp3'
                mimetype = 'audio/mpeg'
            else:
                return jsonify({'error': 'Modified file not found'}), 404
        else:
            path = get_file_path(file_id)
            if not path:
                return jsonify({'error': 'File not found'}), 404
            ext = path.rsplit('.', 1)[1].lower()
            filename = f'video.{ext}'
            mimetype = f'video/{ext}'

        if not os.path.exists(path):
            return jsonify({'error': 'File not found'}), 404
        return send_file(path, as_attachment=True, download_name=filename, mimetype=mimetype)
    except Exception as e:
        print(f'[{timestamp()}] Download error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/frame/<frames_dir_id>/<frame_name>')
def serve_frame(frames_dir_id, frame_name):
    try:
        frame_name = os.path.basename(frame_name)
        frames_dir = f'/tmp/vidlab_{frames_dir_id}_frames'
        frame_path = os.path.join(frames_dir, frame_name)
        if not os.path.exists(frame_path):
            return jsonify({'error': 'Frame not found'}), 404
        return send_file(frame_path, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Scene Prompts (v2) ─────────────────────────────────────────────────────────
# Uses:
#   • BLIP-large (Salesforce/blip-image-captioning-large, ~900 MB) for rich
#     per-frame captions with multi-prompt conditioning.
#   • sentence-transformers all-MiniLM-L6-v2 (~90 MB) for caption embeddings.
#   • Cosine similarity > SCENE_SIM_THRESHOLD to detect scene boundaries.
#   • Batch processing (BATCH_SIZE frames at a time) to stay memory-friendly.
# Frames are deleted immediately after captioning; one representative thumbnail
# per scene is kept for the UI (cleaned up by the background thread after 1h).

_blip_processor = None
_blip_model = None
_st_model = None          # sentence-transformers model
_ai_lock = threading.Lock()

MAX_FRAMES_PER_CHUNK = 100  # frame cap per chunk (CPU/disk safety)
SCENE_FPS_DEFAULT    = 2    # default extraction rate
BATCH_SIZE           = 8    # frames per AI batch
SCENE_SIM_THRESHOLD  = 0.85 # cosine-similarity scene boundary
CHUNK_DURATION       = 300  # seconds per chunk (5 min)
MAX_CHUNKS           = 6    # max chunks to process (30 min total)


def _load_ai_models():
    """Lazy-load BLIP-large and sentence-transformer; thread-safe."""
    global _blip_processor, _blip_model, _st_model
    with _ai_lock:
        if _blip_model is None:
            try:
                from transformers import BlipProcessor, BlipForConditionalGeneration
                import torch
                print(f'[{timestamp()}] Loading BLIP-large model...')
                _blip_processor = BlipProcessor.from_pretrained(
                    'Salesforce/blip-image-captioning-large')
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                _blip_model = BlipForConditionalGeneration.from_pretrained(
                    'Salesforce/blip-image-captioning-large').to(device)
                _blip_model.eval()
                print(f'[{timestamp()}] BLIP-large ready on {device}')
            except Exception as e:
                print(f'[{timestamp()}] BLIP load error: {e}')
                raise
        if _st_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                print(f'[{timestamp()}] Loading sentence-transformer...')
                _st_model = SentenceTransformer('all-MiniLM-L6-v2')
                print(f'[{timestamp()}] sentence-transformer ready')
            except Exception as e:
                print(f'[{timestamp()}] sentence-transformer load error: {e}')
                raise


def _caption_batch(image_paths, conditional_prefix=''):
    """
    Caption a list of images in one batch call.
    Returns a list of caption strings, one per image.
    """
    from PIL import Image
    import torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    images = [Image.open(p).convert('RGB') for p in image_paths]
    if conditional_prefix:
        inputs = _blip_processor(images, [conditional_prefix] * len(images),
                                 return_tensors='pt', padding=True).to(device)
    else:
        inputs = _blip_processor(images, return_tensors='pt', padding=True).to(device)

    with torch.no_grad():
        outs = _blip_model.generate(**inputs, max_new_tokens=60)

    captions = [_blip_processor.decode(o, skip_special_tokens=True).strip()
                for o in outs]
    del images, inputs, outs
    return captions


def _cosine_sim(a, b):
    """Numpy-free cosine similarity between two lists of floats."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _group_by_similarity(embeddings, frame_names, fps_used):
    """
    Group consecutive frames into scenes using cosine similarity.
    Returns a dict:  scene_index → {frame_list, embeddings, start_sec, end_sec}
    """
    if not embeddings:
        return {}

    scenes = {}
    scene_num = 1
    current_frames = [frame_names[0]]
    current_embs   = [embeddings[0]]
    scene_start_idx = 0

    for i in range(1, len(embeddings)):
        sim = _cosine_sim(embeddings[i - 1], embeddings[i])
        if sim >= SCENE_SIM_THRESHOLD:
            current_frames.append(frame_names[i])
            current_embs.append(embeddings[i])
        else:
            scenes[scene_num] = {
                'frame_list':  current_frames,
                'embeddings':  current_embs,
                'start_sec':   round(scene_start_idx / fps_used, 2),
                'end_sec':     round((i - 1) / fps_used, 2),
            }
            scene_num += 1
            current_frames = [frame_names[i]]
            current_embs   = [embeddings[i]]
            scene_start_idx = i

    scenes[scene_num] = {
        'frame_list':  current_frames,
        'embeddings':  current_embs,
        'start_sec':   round(scene_start_idx / fps_used, 2),
        'end_sec':     round((len(embeddings) - 1) / fps_used, 2),
    }
    return scenes


def _build_detailed_prompt(main_caps, env_caps, action_caps):
    """
    Aggregate per-frame captions into a rich scene description covering:
    objects, actions, environment, lighting, mood, and perspective.
    """
    def most_common(lst):
        return max(set(lst), key=lst.count) if lst else ''

    # Pick the most representative caption from each category
    main   = most_common(main_caps)
    env    = most_common(env_caps)
    action = most_common(action_caps)

    # Detect lighting keywords in main captions
    lighting_kw = ['dark', 'bright', 'sunny', 'dim', 'night', 'day', 'shadow',
                    'warm', 'cool', 'golden', 'overcast', 'cloudy', 'neon',
                    'backlit', 'silhouette']
    lighting_found = [w for cap in main_caps for w in cap.lower().split()
                      if w in lighting_kw]
    lighting = most_common(lighting_found) if lighting_found else 'natural'

    # Mood heuristics
    mood_map = {
        'dark': 'somber', 'night': 'mysterious', 'sunny': 'cheerful',
        'bright': 'energetic', 'shadow': 'tense', 'golden': 'warm and nostalgic',
        'neon': 'vibrant', 'overcast': 'melancholic',
    }
    mood = next((mood_map[w] for w in lighting_found if w in mood_map), 'neutral')

    # Perspective heuristics (close-up vs wide)
    close_kw   = ['face', 'hand', 'eye', 'close', 'portrait', 'detail']
    wide_kw    = ['crowd', 'city', 'landscape', 'wide', 'street', 'building',
                  'field', 'sky', 'mountain', 'ocean']
    all_text = ' '.join(main_caps).lower()
    if any(k in all_text for k in close_kw):
        perspective = 'close-up shot'
    elif any(k in all_text for k in wide_kw):
        perspective = 'wide establishing shot'
    else:
        perspective = 'medium shot'

    parts = [main]
    if env and env != main:
        parts.append(f'Environment: {env}.')
    if action and action != main:
        parts.append(f'Action: {action}.')
    parts.append(f'Lighting: {lighting}.')
    parts.append(f'Mood: {mood}.')
    parts.append(f'Perspective: {perspective}.')

    return ' '.join(parts)


def _caption_and_group_frames(frames_dir, fps_used, chunk_id, chunk_offset_sec=0.0):
    """
    Run BLIP captioning + cosine-similarity grouping on all JPEGs in frames_dir.
    Timestamps are offset by chunk_offset_sec so multi-chunk videos report
    absolute video times.

    Returns:
        result_scenes  – dict  scene_key → scene data dict
        kept_thumbs    – set   of frame basenames that were kept as thumbnails
        total_frames   – int
    Raises MemoryError / Exception on fatal failure.
    Deletes all non-thumbnail frames from disk before returning.
    """
    jpg_files = sorted(glob_module.glob(f'{frames_dir}/scene_*.jpg'))

    # Cap per-chunk frames
    if len(jpg_files) > MAX_FRAMES_PER_CHUNK:
        for excess in jpg_files[MAX_FRAMES_PER_CHUNK:]:
            try: os.remove(excess)
            except Exception: pass
        jpg_files = jpg_files[:MAX_FRAMES_PER_CHUNK]

    if not jpg_files:
        return {}, set(), 0

    frame_names  = [os.path.basename(f) for f in jpg_files]
    total_frames = len(jpg_files)

    all_main_caps, all_env_caps, all_action_caps, all_embeddings = [], [], [], []
    batches = [jpg_files[i:i + BATCH_SIZE] for i in range(0, total_frames, BATCH_SIZE)]

    for b_idx, batch_paths in enumerate(batches):
        n = len(batch_paths)
        try:
            main_caps   = _caption_batch(batch_paths)
            env_caps    = _caption_batch(batch_paths, 'the environment is')
            action_caps = _caption_batch(batch_paths, 'the action in this image is')
        except Exception as e:
            print(f'[{timestamp()}] Chunk {chunk_id} batch {b_idx} caption error: {e}')
            main_caps   = ['a video scene'] * n
            env_caps    = ['an environment'] * n
            action_caps = ['an action'] * n

        all_main_caps.extend(main_caps)
        all_env_caps.extend(env_caps)
        all_action_caps.extend(action_caps)

        try:
            embs = _st_model.encode(main_caps, convert_to_numpy=True, show_progress_bar=False)
            for emb in embs:
                all_embeddings.append(emb.tolist())
        except Exception:
            for _ in batch_paths:
                all_embeddings.append([0.0] * 384)

    raw_scenes = _group_by_similarity(all_embeddings, frame_names, fps_used)

    # Derive a stable dir-id from the frames_dir path
    dir_id = os.path.basename(frames_dir).replace('vidlab_', '').replace('_scene_frames', '')

    result_scenes = {}
    kept_thumbs   = set()

    for sn, scene in raw_scenes.items():
        fl   = scene['frame_list']
        idxs = [frame_names.index(f) for f in fl if f in frame_names]

        main_c = [all_main_caps[i]   for i in idxs if i < len(all_main_caps)]
        env_c  = [all_env_caps[i]    for i in idxs if i < len(all_env_caps)]
        act_c  = [all_action_caps[i] for i in idxs if i < len(all_action_caps)]

        prompt = _build_detailed_prompt(main_c, env_c, act_c)
        thumb  = fl[0]
        kept_thumbs.add(thumb)

        result_scenes[str(sn)] = {
            'frame_list':      fl,
            'prompt':          prompt,
            'scene_start_sec': round(scene['start_sec'] + chunk_offset_sec, 2),
            'scene_end_sec':   round(scene['end_sec']   + chunk_offset_sec, 2),
            'frames_dir_id':   dir_id,
            'thumbnail':       thumb,
            'chunk_id':        chunk_id,
        }

    # Immediately delete non-thumbnail frames
    for fname in frame_names:
        if fname not in kept_thumbs:
            fpath = os.path.join(frames_dir, fname)
            try:
                if os.path.exists(fpath): os.remove(fpath)
            except Exception as e:
                print(f'[{timestamp()}] Frame delete error {fname}: {e}')

    return result_scenes, kept_thumbs, total_frames


def _extract_frames_ffmpeg(src_path, out_dir, fps, timeout_secs=180):
    """
    Run ffmpeg to extract frames from src_path into out_dir.
    Returns (ok: bool, err_msg: str | None, detected_duration: float | None).
    """
    os.makedirs(out_dir, exist_ok=True)
    cmd = ['ffmpeg', '-y', '-i', src_path,
           '-vf', f'fps={fps}', '-q:v', '5',
           f'{out_dir}/scene_%04d.jpg']
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True, bufsize=1)
    except FileNotFoundError:
        return False, 'FFmpeg not installed', None

    total_dur = None
    start     = time.time()
    for line in proc.stderr:
        if time.time() - start > timeout_secs:
            proc.kill(); proc.wait()
            return False, f'Frame extraction timed out after {timeout_secs}s', total_dur
        if total_dur is None:
            d = _parse_duration(line)
            if d and d > 0: total_dur = d
    proc.wait()
    if proc.returncode != 0:
        return False, 'Frame extraction failed (FFmpeg error)', total_dur
    return True, None, total_dur


@app.route('/analyze-scenes', methods=['POST'])
def analyze_scenes():
    """
    SSE-streaming scene prompt generation with automatic video splitting.

    Pipeline:
      1. Probe video duration with ffprobe.
      2. Split videos > CHUNK_DURATION (5 min) into ≤ MAX_CHUNKS chunks via
         FFmpeg stream-copy (-c copy). Short videos skip splitting.
      3. For each chunk (sequentially to protect CPU/disk):
         a. Extract frames at `fps` (default 2, max 100 frames/chunk).
         b. Run BLIP-large in batches of 8 (3 prompt variants per frame).
         c. Embed captions with all-MiniLM-L6-v2.
         d. Group frames into scenes by cosine similarity ≥ 0.85.
         e. Build structured prompt per scene.
         f. Delete chunk video + non-thumbnail frames immediately.
      4. Flatten all chunk scenes into a single numbered scene dict.
      5. Return aggregated JSON with both `scenes` (flat) and `chunks` (metadata).
    """
    data = request.get_json()
    if not data or 'file_id' not in data:
        return jsonify({'error': 'Missing file_id'}), 400

    file_id  = data['file_id']
    fps      = float(data.get('fps', SCENE_FPS_DEFAULT))
    fps      = max(0.2, min(fps, 2.0))
    filepath = get_file_path(file_id)
    if not filepath:
        return jsonify({'error': 'File not found'}), 404

    run_id = str(uuid.uuid4())

    def generate():
        yield _sse({'percent': 2, 'step': 'Preparing scene analysis...'})
        pre_process_cleanup()

        # ── Phase 1: Probe duration (2-6%) ────────────────────────────────────
        yield _sse({'percent': 4, 'step': 'Probing video duration...'})
        try:
            import json as _json
            probe = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                 '-show_format', filepath],
                capture_output=True, text=True, timeout=30
            )
            info         = _json.loads(probe.stdout)
            total_dur    = float(info.get('format', {}).get('duration', 0))
        except Exception:
            total_dur = 0.0   # Unknown duration — treat as short video

        # ── Phase 2: Plan chunks (6-10%) ──────────────────────────────────────
        if total_dur > CHUNK_DURATION:
            n_chunks_raw = int(total_dur / CHUNK_DURATION) + (1 if total_dur % CHUNK_DURATION else 0)
            n_chunks     = min(n_chunks_raw, MAX_CHUNKS)
            if n_chunks < n_chunks_raw:
                capped_msg = (f' (capped at {MAX_CHUNKS} chunks = '
                              f'{MAX_CHUNKS * CHUNK_DURATION // 60} min)')
            else:
                capped_msg = ''
            yield _sse({'percent': 6, 'step': (
                f'Video is {int(total_dur)}s — splitting into '
                f'{n_chunks} × 5-min chunks{capped_msg}...'
            )})
        else:
            n_chunks = 1
            yield _sse({'percent': 6, 'step': f'Video is {int(total_dur)}s — processing as single chunk...'})

        # ── Phase 3: Load AI models once (10-18%) ─────────────────────────────
        yield _sse({'percent': 10, 'step': 'Loading AI models (BLIP-large + sentence-transformer)...'})
        try:
            _load_ai_models()
        except ImportError:
            yield _sse({'error': 'AI libraries missing. Install torch, transformers, sentence-transformers.'})
            return
        except MemoryError:
            yield _sse({'error': 'Not enough RAM to load AI models. Try a shorter video.'})
            return
        except Exception as e:
            yield _sse({'error': f'Model load failed: {str(e)[:200]}'})
            return

        yield _sse({'percent': 18, 'step': f'Models ready. Processing {n_chunks} chunk(s)...'})

        # ── Phase 4: Process chunks sequentially (18-96%) ─────────────────────
        # Each chunk occupies an equal slice of the 18-96% range.
        chunk_pct_span = (96 - 18) / n_chunks

        all_scenes   = {}   # flattened scene_key → scene data (across all chunks)
        chunks_meta  = []   # per-chunk summary for the response
        global_scene = 0    # scene counter across chunks

        for chunk_idx in range(n_chunks):
            chunk_num    = chunk_idx + 1
            chunk_start  = chunk_idx * CHUNK_DURATION
            chunk_pct_lo = int(18 + chunk_idx * chunk_pct_span)
            chunk_pct_hi = int(18 + (chunk_idx + 1) * chunk_pct_span)

            frames_dir_id = f'{run_id}_c{chunk_num}'
            frames_dir    = f'/tmp/vidlab_{frames_dir_id}_scene_frames'
            chunk_path    = f'/tmp/vidlab_{run_id}_chunk{chunk_num}.mp4'

            # ── 4a: Split chunk from source video ─────────────────────────────
            if n_chunks == 1:
                # No splitting needed
                src_for_frames = filepath
                chunk_label    = f'Processing video ({int(total_dur)}s)...'
            else:
                yield _sse({'percent': chunk_pct_lo, 'step': (
                    f'Chunk {chunk_num}/{n_chunks}: cutting '
                    f'{int(chunk_start)}s – {int(chunk_start + CHUNK_DURATION)}s...'
                )})
                split_cmd = [
                    'ffmpeg', '-y', '-i', filepath,
                    '-ss', str(chunk_start), '-t', str(CHUNK_DURATION),
                    '-c', 'copy', chunk_path
                ]
                try:
                    split_proc = subprocess.run(
                        split_cmd, capture_output=True, text=True, timeout=120
                    )
                    if split_proc.returncode != 0 or not os.path.exists(chunk_path):
                        yield _sse({'error': f'Chunk {chunk_num} split failed. Try a shorter video.'})
                        return
                except subprocess.TimeoutExpired:
                    yield _sse({'error': f'Chunk {chunk_num} split timed out.'})
                    return
                except OSError as e:
                    if 'No space left' in str(e):
                        yield _sse({'error': 'Disk quota exceeded during chunk split. Use a lower FPS or shorter video.'})
                    else:
                        yield _sse({'error': f'System error: {str(e)[:200]}'})
                    return

                src_for_frames = chunk_path
                chunk_label    = f'Chunk {chunk_num}/{n_chunks}'

            # ── 4b: Extract frames from this chunk ────────────────────────────
            pct_extract = chunk_pct_lo + int(chunk_pct_span * 0.15)
            yield _sse({'percent': pct_extract, 'step': (
                f'{chunk_label}: extracting frames at {fps} fps...'
            )})

            ok, err_msg, _ = _extract_frames_ffmpeg(src_for_frames, frames_dir, fps)
            if not ok:
                # Delete chunk video if it was created
                if n_chunks > 1:
                    try: os.remove(chunk_path)
                    except Exception: pass
                remove_dir(frames_dir)
                yield _sse({'error': f'{chunk_label}: {err_msg}'})
                return

            # Delete the chunk video file immediately to reclaim disk
            if n_chunks > 1:
                try: os.remove(chunk_path)
                except Exception: pass

            jpg_count = len(glob_module.glob(f'{frames_dir}/scene_*.jpg'))
            if jpg_count == 0:
                remove_dir(frames_dir)
                # No frames — skip this chunk (happens at end of video sometimes)
                chunks_meta.append({
                    'chunk_id':    chunk_num,
                    'start_sec':   chunk_start,
                    'end_sec':     chunk_start + CHUNK_DURATION,
                    'scene_count': 0,
                    'frame_count': 0,
                })
                continue

            # ── 4c: Caption + group frames (the heavy AI step) ────────────────
            pct_caption = chunk_pct_lo + int(chunk_pct_span * 0.25)
            yield _sse({'percent': pct_caption, 'step': (
                f'{chunk_label}: captioning {min(jpg_count, MAX_FRAMES_PER_CHUNK)} frames...'
            )})

            try:
                chunk_scenes, _thumbs, n_frames = _caption_and_group_frames(
                    frames_dir,
                    fps_used        = fps,
                    chunk_id        = chunk_num,
                    chunk_offset_sec = chunk_start,
                )
            except MemoryError:
                remove_dir(frames_dir)
                yield _sse({'error': f'{chunk_label}: out of memory. Try a lower FPS.'})
                return
            except Exception as e:
                remove_dir(frames_dir)
                yield _sse({'error': f'{chunk_label}: processing failed — {str(e)[:200]}'})
                return

            # Merge chunk scenes into global flat dict (renumber sequentially)
            for _, scene in chunk_scenes.items():
                global_scene += 1
                all_scenes[str(global_scene)] = scene

            chunks_meta.append({
                'chunk_id':    chunk_num,
                'start_sec':   chunk_start,
                'end_sec':     min(chunk_start + CHUNK_DURATION, total_dur) if total_dur else chunk_start + CHUNK_DURATION,
                'scene_count': len(chunk_scenes),
                'frame_count': n_frames,
            })

            pct_done = chunk_pct_hi
            yield _sse({'percent': pct_done, 'step': (
                f'{chunk_label}: found {len(chunk_scenes)} scene(s). '
                f'{"Next chunk..." if chunk_num < n_chunks else "Finalizing..."}'
            )})

        # ── Phase 5: Return aggregated result (96-100%) ────────────────────────
        total_frames  = sum(c['frame_count'] for c in chunks_meta)
        total_scenes  = len(all_scenes)
        is_multi      = n_chunks > 1

        # frames_dir_id for backward-compat (use first chunk's dir id)
        first_dir_id = f'{run_id}_c1'

        print(f'[{timestamp()}] Scene analysis done: {total_scenes} scenes across '
              f'{n_chunks} chunk(s), {total_frames} total frames')

        yield _sse({'percent': 100, 'done': True, 'result': {
            'scenes':          all_scenes,
            'chunks':          chunks_meta,
            'total_frames':    total_frames,
            'total_scenes':    total_scenes,
            'total_chunks':    n_chunks,
            'is_multi_chunk':  is_multi,
            'frames_dir_id':   first_dir_id,   # backward compat
            'video_duration':  round(total_dur, 2),
        }})

    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/scene-frame/<frames_dir_id>/<frame_name>')
def serve_scene_frame(frames_dir_id, frame_name):
    """Serve a scene thumbnail image."""
    try:
        frame_name = os.path.basename(frame_name)
        frames_dir = f'/tmp/vidlab_{frames_dir_id}_scene_frames'
        frame_path = os.path.join(frames_dir, frame_name)
        if not os.path.exists(frame_path):
            return jsonify({'error': 'Frame not found'}), 404
        return send_file(frame_path, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Transcript (Whisper) ───────────────────────────────────────────────────────
# Uses openai-whisper (tiny model, ~75 MB) running fully on-device (CPU).
# Audio is extracted to 16 kHz mono WAV, transcribed, then the WAV is deleted.
# Duration is capped at TRANSCRIPT_MAX_DURATION (5 min) to protect free-tier RAM.

_whisper_model = None
_whisper_lock  = threading.Lock()

TRANSCRIPT_MAX_DURATION = 300     # 5 minutes in seconds (per-chunk)
TRANSCRIPT_MAX_CHUNKS   = 12      # max chunks ≈ 60 min total


def _load_whisper():
    """Lazy-load Whisper tiny model; thread-safe."""
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            try:
                import whisper as _whisper
                print(f'[{timestamp()}] Loading Whisper tiny model...')
                _whisper_model = _whisper.load_model('tiny')
                print(f'[{timestamp()}] Whisper tiny model loaded')
            except Exception as e:
                print(f'[{timestamp()}] Whisper load error: {e}')
                raise


@app.route('/generate-transcript', methods=['POST'])
def generate_transcript():
    """
    SSE-streaming transcript generation route.
    Pipeline:
      1. Probe video duration.
      2. If > 5 min, split into chunks; for each chunk:
         a. FFmpeg stream-copy the segment.
         b. Extract 16 kHz mono WAV.
         c. Transcribe with Whisper (English).
         d. Offset timestamps by chunk start.
         e. Clean up chunk files immediately.
      3. Merge adjacent segments across chunk boundaries.
      4. Format and return unified transcript.
    """
    data = request.get_json()
    if not data or 'file_id' not in data:
        return jsonify({'error': 'Missing file_id'}), 400

    file_id  = data['file_id']
    filepath = get_file_path(file_id)
    if not filepath:
        return jsonify({'error': 'File not found'}), 404

    def generate():
        yield _sse({'percent': 2, 'step': 'Preparing transcript generation...'})
        pre_process_cleanup()

        # ── Phase 1: Probe duration & chunk planning (2-10%) ─────────────────
        yield _sse({'percent': 5, 'step': 'Checking video duration...'})
        try:
            import json as _json
            probe = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                 '-show_format', filepath],
                capture_output=True, text=True, timeout=30
            )
            info     = _json.loads(probe.stdout)
            duration = float(info.get('format', {}).get('duration', 0))
        except Exception:
            duration = 0

        if duration > TRANSCRIPT_MAX_DURATION:
            n_chunks_raw = int(duration / TRANSCRIPT_MAX_DURATION) + (1 if duration % TRANSCRIPT_MAX_DURATION else 0)
            n_chunks     = min(n_chunks_raw, TRANSCRIPT_MAX_CHUNKS)
            if n_chunks < n_chunks_raw:
                capped_msg = (f' (capped at {TRANSCRIPT_MAX_CHUNKS} chunks = '
                              f'{TRANSCRIPT_MAX_CHUNKS * TRANSCRIPT_MAX_DURATION // 60} min)')
            else:
                capped_msg = ''
            yield _sse({'percent': 8, 'step': (
                f'Video is {int(duration)}s — splitting into '
                f'{n_chunks} × 5-min chunks{capped_msg}...'
            )})
        else:
            n_chunks = 1
            yield _sse({'percent': 8, 'step': f'Video is {int(duration)}s — transcribing in one pass...'})

        # ── Phase 2: Load Whisper model once (8-15%) ─────────────────────────
        yield _sse({'percent': 10, 'step': 'Loading Whisper model...'})
        try:
            _load_whisper()
        except ImportError:
            yield _sse({'error': 'openai-whisper is not installed.'})
            return
        except MemoryError:
            yield _sse({'error': 'Not enough RAM to load Whisper. Try a shorter video.'})
            return
        except Exception as e:
            yield _sse({'error': f'Whisper model load failed: {str(e)[:200]}'})
            return

        yield _sse({'percent': 15, 'step': f'Whisper ready. Transcribing {n_chunks} chunk(s)...'})

        # ── Phase 3: Process chunks sequentially (15-96%) ────────────────────
        run_id = str(uuid.uuid4())
        chunk_pct_span = (96 - 15) / n_chunks

        all_raw_segs   = []
        all_raw_texts  = []
        total_word_count = 0
        detected_lang   = 'unknown'

        for chunk_idx in range(n_chunks):
            chunk_num    = chunk_idx + 1
            chunk_start  = chunk_idx * TRANSCRIPT_MAX_DURATION
            chunk_pct_lo = int(15 + chunk_idx * chunk_pct_span)

            chunk_path = f'/tmp/vidlab_{run_id}_chunk{chunk_num}.mp4'
            wav_path   = f'/tmp/vidlab_{run_id}_chunk{chunk_num}_audio.wav'

            # ── 3a: Split chunk from source video ────────────────────────────
            if n_chunks == 1:
                src_for_audio = filepath
            else:
                yield _sse({'percent': chunk_pct_lo, 'step': (
                    f'Chunk {chunk_num}/{n_chunks}: cutting '
                    f'{int(chunk_start)}s – {int(chunk_start + TRANSCRIPT_MAX_DURATION)}s...'
                )})
                split_cmd = [
                    'ffmpeg', '-y', '-i', filepath,
                    '-ss', str(chunk_start), '-t', str(TRANSCRIPT_MAX_DURATION),
                    '-c', 'copy', chunk_path
                ]
                try:
                    split_proc = subprocess.run(split_cmd, capture_output=True, text=True, timeout=120)
                    if split_proc.returncode != 0 or not os.path.exists(chunk_path):
                        yield _sse({'error': f'Chunk {chunk_num} split failed. Try a shorter video.'})
                        return
                except subprocess.TimeoutExpired:
                    yield _sse({'error': f'Chunk {chunk_num} split timed out.'})
                    return
                except OSError as e:
                    if 'No space left' in str(e):
                        yield _sse({'error': 'Disk quota exceeded during chunk split.'})
                    else:
                        yield _sse({'error': f'System error: {str(e)[:200]}'})
                    return

                src_for_audio = chunk_path

            # ── 3b: Extract audio from this chunk ────────────────────────────
            yield _sse({'percent': chunk_pct_lo + int(chunk_pct_span * 0.15), 'step': (
                f'Chunk {chunk_num}/{n_chunks}: extracting audio...'
            )})
            cmd = ['ffmpeg', '-y', '-i', src_for_audio,
                   '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                   wav_path]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if proc.returncode != 0:
                    if n_chunks > 1:
                        try: os.remove(chunk_path)
                        except: pass
                    yield _sse({'error': f'Chunk {chunk_num}: audio extraction failed. The chunk may have no audio track.'})
                    return
            except subprocess.TimeoutExpired:
                try: os.remove(wav_path)
                except: pass
                if n_chunks > 1:
                    try: os.remove(chunk_path)
                    except: pass
                yield _sse({'error': 'Audio extraction timed out. Try a shorter video.'})
                return
            except FileNotFoundError:
                yield _sse({'error': 'FFmpeg not installed.'})
                return
            except OSError as e:
                try: os.remove(wav_path)
                except: pass
                if n_chunks > 1:
                    try: os.remove(chunk_path)
                    except: pass
                if 'No space left' in str(e):
                    yield _sse({'error': 'Disk quota exceeded.'})
                else:
                    yield _sse({'error': f'System error: {str(e)[:200]}'})
                return

            # Delete chunk video immediately to reclaim disk
            if n_chunks > 1:
                try: os.remove(chunk_path)
                except: pass

            if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
                try: os.remove(wav_path)
                except: pass
                if chunk_num < n_chunks:
                    continue   # silent mid-video chunk — skip
                yield _sse({'error': 'No audio could be extracted. The video may be silent.'})
                return

            # ── 3c: Transcribe this chunk ────────────────────────────────────
            pct_transcribe = chunk_pct_lo + int(chunk_pct_span * 0.40)
            yield _sse({'percent': pct_transcribe, 'step': (
                f'Chunk {chunk_num}/{n_chunks}: transcribing...'
            )})
            try:
                result        = _whisper_model.transcribe(wav_path, language='en', fp16=False)
                raw_text      = result.get('text', '').strip()
                chunk_lang    = result.get('language', 'unknown')
                raw_segs      = result.get('segments', [])
            except MemoryError:
                yield _sse({'error': 'Out of memory during transcription. Try a shorter video.'})
                return
            except Exception as e:
                yield _sse({'error': f'Chunk {chunk_num} transcription failed: {str(e)[:200]}'})
                return
            finally:
                try: os.remove(wav_path)
                except: pass

            if chunk_lang != 'unknown':
                detected_lang = chunk_lang

            # ── 3d: Offset timestamps by chunk start ─────────────────────────
            if chunk_start > 0:
                for seg in raw_segs:
                    seg['start'] += chunk_start
                    seg['end']   += chunk_start

            if raw_text:
                all_raw_texts.append(raw_text)
                all_raw_segs.extend(raw_segs)
                total_word_count += len(raw_text.split())

        if not all_raw_segs and not all_raw_texts:
            yield _sse({'error': 'Whisper could not detect any speech in this video.'})
            return

        # ── Phase 4: Format merged segments (96-98%) ─────────────────────────
        yield _sse({'percent': 96, 'step': 'Formatting transcript...'})

        def _sec_to_mmss(s):
            m = int(s) // 60
            sec = int(s) % 60
            return f'{m:02d}:{sec:02d}'

        # Merge segments within 1.5s of each other into paragraphs
        paragraphs = []
        for seg in all_raw_segs:
            txt = seg.get('text', '').strip()
            if not txt:
                continue
            start = seg['start']
            end   = seg['end']
            if paragraphs and (start - paragraphs[-1]['end']) < 1.5:
                paragraphs[-1]['text'] += ' ' + txt
                paragraphs[-1]['end']   = end
            else:
                paragraphs.append({'start': start, 'end': end, 'text': txt})

        if not paragraphs and all_raw_texts:
            combined = ' '.join(all_raw_texts)
            paragraphs = [{'start': 0.0, 'end': duration, 'text': combined}]

        formatted_blocks = []
        api_segments     = []
        for para in paragraphs:
            ts    = _sec_to_mmss(para['start'])
            block = f'Speaker 1 ({ts})\n{para["text"]}'
            formatted_blocks.append(block)
            api_segments.append({
                'start':   round(para['start'], 2),
                'end':     round(para['end'],   2),
                'speaker': 'Speaker 1',
                'ts':      ts,
                'text':    para['text'],
            })

        formatted_transcript = '\n\n'.join(formatted_blocks)

        # Write .txt file
        yield _sse({'percent': 98, 'step': 'Saving transcript file...'})
        txt_filename = f'vidlab_{file_id}_transcript.txt'
        txt_path     = f'/tmp/{txt_filename}'
        try:
            with open(txt_path, 'w', encoding='utf-8') as fh:
                fh.write(formatted_transcript)
        except OSError as e:
            print(f'[{timestamp()}] Could not write transcript .txt: {e}')
            txt_filename = None

        print(f'[{timestamp()}] Transcript done: {total_word_count} words, '
              f'{len(api_segments)} segments, lang={detected_lang}, chunks={n_chunks}')

        yield _sse({'percent': 100, 'done': True, 'result': {
            'file_id':    file_id,
            'transcript': formatted_transcript,
            'language':   detected_lang,
            'segments':   api_segments,
            'word_count': total_word_count,
            'txt_file':   f'/download-transcript/{txt_filename}' if txt_filename else None,
        }})

    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/download-transcript/<filename>')
def download_transcript_file(filename):
    """Serve a generated transcript .txt file from /tmp."""
    try:
        safe_name = os.path.basename(filename)
        if not safe_name.startswith('vidlab_') or not safe_name.endswith('_transcript.txt'):
            return jsonify({'error': 'Invalid filename'}), 400
        path = f'/tmp/{safe_name}'
        if not os.path.exists(path):
            return jsonify({'error': 'Transcript file not found or expired'}), 404
        return send_file(path, mimetype='text/plain',
                         as_attachment=True, download_name='transcript.txt')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    nuke_frame_dirs()
    cleanup_old_files_background()
    port = int(os.environ.get('PORT', 8000))
    print(f'[{timestamp()}] VidLab starting on port {port}')
    # threaded=True lets Werkzeug serve multiple requests concurrently and,
    # critically, keep streaming large file responses (e.g. 4K downloads) without
    # blocking the next request or being killed by other concurrent requests.
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
