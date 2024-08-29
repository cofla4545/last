from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
import os
import base64
import image
import video
import shutil
import threading

app = Flask(__name__)
socketio = SocketIO(app)

# 파일 업로드를 위한 디렉토리 설정
TRAIN_FOLDER = './static/train/'
INPUT_FOLDER = './static/input/'
OUTPUT_FOLDER = './static/output/'
app.config['TRAIN_FOLDER'] = TRAIN_FOLDER
app.config['INPUT_FOLDER'] = INPUT_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/camera')
def camera():
    return render_template('camera.html')

@app.route('/train')
def train():
    return render_template('train.html')

@app.route('/train_camera')
def train_camera():
    return render_template('train_camera.html')

@app.route('/train_gallery')
def train_gallery():
    return render_template('train_gallery.html')

@app.route('/gallery')
def gallery():
    return render_template('gallery.html')

@app.route('/gallery_convert')
def gallery_convert():
    # OUTPUT_FOLDER에서 가장 최신 파일을 검색
    output_files = os.listdir(app.config['OUTPUT_FOLDER'])
    output_files = [f for f in output_files if os.path.isfile(os.path.join(app.config['OUTPUT_FOLDER'], f))]
    if not output_files:
        return "No files found in the output directory.", 404

    # 파일 수정 시간 기준으로 정렬하여 최신 파일을 찾음
    latest_file = max(output_files, key=lambda f: os.path.getmtime(os.path.join(app.config['OUTPUT_FOLDER'], f)))
    latest_file_url = url_for('send_output', filename=latest_file)

    # 최신 파일의 URL을 템플릿으로 전달
    return render_template('gallery_convert.html', result_file_url=latest_file_url)

@app.route('/save_image', methods=['POST'])
def save_image():
    image_data = request.form['image']
    image_data = image_data.replace('data:image/png;base64,', '')
    image_data = base64.b64decode(image_data)

    image_dir = app.config['TRAIN_FOLDER']
    image_path = os.path.join(image_dir, 'train_image.jpg')

    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    with open(image_path, 'wb') as f:
        f.write(image_data)

    return redirect(url_for('index'))  # 이미지 저장 후 index.html로 리디렉션

@app.route('/save_exclusion_image', methods=['POST'])
def save_exclusion_image():
    if 'gallery_photo' not in request.files:
        return jsonify({'error': 'No photo part in the request'}), 400

    photo = request.files['gallery_photo']
    if photo.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = 'train_image.jpg'  # 변경된 파일명
    save_path = os.path.join(app.config['TRAIN_FOLDER'], filename)
    app.logger.info(f'Saving photo to {save_path}')
    try:
        photo.save(save_path)
        app.logger.info('Photo successfully saved')
        return jsonify({'message': 'File successfully uploaded', 'redirect_url': url_for('index')}), 200
    except Exception as e:
        app.logger.error(f'Error saving photo: {e}')
        return jsonify({'error': 'Failed to save file'}), 500

@app.route('/convert_image', methods=['POST'])
def convert_image():
    output_folder = app.config['OUTPUT_FOLDER']
    if os.path.exists(output_folder):
        for filename in os.listdir(output_folder):
            file_path = os.path.join(output_folder, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error occurred while deleting file {file_path}: {e}")

    if 'image' not in request.files:
        return jsonify({'error': 'No image part in the request'}), 400

    image_data = request.files['image']
    if image_data.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    image_path = os.path.join(app.config['INPUT_FOLDER'], 'input_image.jpg')
    image_data.save(image_path)

    try:
        learning_image_path = os.path.join(app.config['TRAIN_FOLDER'], 'train_image.jpg')
        output_image_path = os.path.join(app.config['OUTPUT_FOLDER'], 'output_image.jpg')
        image.process_images(learning_image_path, image_path, output_image_path)
    except Exception as e:
        print(f"Error occurred: {e}")
        return f"An error occurred while processing the image: {e}", 500

    return redirect(url_for('gallery_convert'))


@app.route('/convert_video', methods=['POST'])
def convert_video():
    output_folder = app.config['OUTPUT_FOLDER']

    # 출력 폴더에 이전 결과 파일이 있다면 삭제
    if os.path.exists(output_folder):
        for filename in os.listdir(output_folder):
            file_path = os.path.join(output_folder, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error occurred while deleting file {file_path}: {e}")

    if 'video' not in request.files:
        return jsonify({'error': 'No video part in the request'}), 400

    video_data = request.files['video']
    if video_data.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    video_path = os.path.join(app.config['INPUT_FOLDER'], 'input_video.mp4')
    video_data.save(video_path)

    try:
        learning_image_path = os.path.join(app.config['TRAIN_FOLDER'], 'train_image.jpg')
        output_video_path = os.path.join(app.config['OUTPUT_FOLDER'], 'output_video.mp4')
        output_video_with_audio_path = os.path.join(app.config['OUTPUT_FOLDER'], 'output_video_with_audio.mp4')

        threading.Thread(target=video.process_video, args=(
            learning_image_path, video_path, output_video_path, output_video_with_audio_path, socketio, app)).start()

    except Exception as e:
        print(f"Error occurred: {e}")
        return jsonify({'error': f"An error occurred while processing the video: {e}"}), 500

    return jsonify({'message': 'Video processing started'}), 200


@app.route('/output/<filename>')
def send_output(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename)

@app.route('/camera_video_convert', methods=['POST'])
def camera_video_convert():
    input_folder = app.config['INPUT_FOLDER']

    if os.path.exists(input_folder):
        shutil.rmtree(input_folder)
    os.makedirs(input_folder)

    if 'video' not in request.files:
        return jsonify({'error': 'No video part in the request'}), 400

    video_data = request.files['video']
    if video_data.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    video_path = os.path.join(input_folder, 'input_webcam.mp4')
    video_data.save(video_path)

    try:
        converted_video_path = video_path.replace('.mp4', '_converted.mp4')
        os.system(f"ffmpeg -i {video_path} {converted_video_path}")

        learning_image_path = os.path.join(app.config['TRAIN_FOLDER'], 'train_image.jpg')
        output_video_path = os.path.join(app.config['OUTPUT_FOLDER'], 'output_webcam.mp4')
        output_video_with_audio_path = os.path.join(app.config['OUTPUT_FOLDER'], 'output_webcam_with_audio.mp4')

        threading.Thread(target=video.process_video, args=(
            learning_image_path, converted_video_path, output_video_path, output_video_with_audio_path, socketio, app)).start()

    except Exception as e:
        print(f"Error occurred: {e}")
        return jsonify({'error': f"An error occurred while processing the video: {e}"}), 500

    return jsonify({'redirect_url': url_for('camera_convert', video_url=url_for('send_output', filename='output_webcam_with_audio.mp4'))})

@app.route('/camera_image_convert', methods=['POST'])
def camera_image_convert():
    input_folder = app.config['INPUT_FOLDER']

    if os.path.exists(input_folder):
        shutil.rmtree(input_folder)
    os.makedirs(input_folder)

    if 'image' not in request.files:
        return jsonify({'error': 'No image part in the request'}), 400

    image_data = request.files['image']
    if image_data.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    image_path = os.path.join(input_folder, 'input_image_from_camera.jpg')
    image_data.save(image_path)

    try:
        learning_image_path = os.path.join(app.config['TRAIN_FOLDER'], 'train_image.jpg')
        output_image_path = os.path.join(app.config['OUTPUT_FOLDER'], 'output_image_from_camera.jpg')
        image.process_images(learning_image_path, image_path, output_image_path)

    except Exception as e:
        print(f"Error occurred: {e}")
        return jsonify({'error': f"An error occurred while processing the image: {e}"}), 500

    return jsonify({'redirect_url': url_for('camera_convert',
                                            image_url=url_for('send_output', filename='output_image_from_camera.jpg'))})

@app.route('/camera_convert')
def camera_convert():
    output_files = os.listdir(app.config['OUTPUT_FOLDER'])
    output_files = [f for f in output_files if os.path.isfile(os.path.join(app.config['OUTPUT_FOLDER'], f))]
    if not output_files:
        return "No files found in the output directory.", 404

    latest_file = max(output_files, key=lambda f: os.path.getmtime(os.path.join(app.config['OUTPUT_FOLDER'], f)))
    latest_file_url = url_for('send_output', filename=latest_file)

    return render_template('camera_convert.html', result_file_url=latest_file_url)

@socketio.on('progress')
def handle_progress(data):
    progress = data.get('progress', 0)
    app.logger.info(f'Progress: {progress}%')
    emit('progress', {'progress': progress})
    if progress == 100:
        emit('complete')

@socketio.on('connect')
def handle_connect():
    app.logger.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    app.logger.info('Client disconnected')



if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5002, allow_unsafe_werkzeug=True)
