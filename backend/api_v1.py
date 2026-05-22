from flask import Blueprint

api = Blueprint('api_v1', __name__, url_prefix='/api/v1')


@api.route('/upload', methods=['POST'])
def upload_v1():
    from main import upload
    return upload()


@api.route('/analyze', methods=['POST'])
def analyze_v1():
    from main import analyze
    return analyze()


@api.route('/duplicate', methods=['POST'])
def duplicate_v1():
    from main import duplicate
    return duplicate()


@api.route('/modify', methods=['POST'])
def modify_v1():
    from main import modify
    return modify()


@api.route('/download/<file_id>')
def download_v1(file_id):
    from main import download
    return download(file_id)


@api.route('/frame/<frames_dir_id>/<frame_name>')
def serve_frame_v1(frames_dir_id, frame_name):
    from main import serve_frame
    return serve_frame(frames_dir_id, frame_name)


@api.route('/analyze-scenes', methods=['POST'])
def analyze_scenes_v1():
    from main import analyze_scenes
    return analyze_scenes()


@api.route('/scene-frame/<frames_dir_id>/<frame_name>')
def scene_frame_v1(frames_dir_id, frame_name):
    from main import serve_scene_frame
    return serve_scene_frame(frames_dir_id, frame_name)


@api.route('/generate-transcript', methods=['POST'])
def generate_transcript_v1():
    from main import generate_transcript
    return generate_transcript()


@api.route('/download-transcript/<filename>')
def download_transcript_v1(filename):
    from main import download_transcript_file
    return download_transcript_file(filename)
