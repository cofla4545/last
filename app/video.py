import os
import cv2
import numpy as np
from insightface.app import FaceAnalysis
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm
import warnings
from moviepy.editor import VideoFileClip, concatenate_videoclips
from flask import url_for, Flask


warnings.filterwarnings("ignore", category=FutureWarning)

app = FaceAnalysis(providers=['CPUExecutionProvider'])
app.prepare(ctx_id=0, det_size=(640, 640))

def get_face_embedding(image_path):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Error loading image: {image_path}")
    faces = app.get(image)
    if len(faces) == 0:
        raise ValueError("No face detected in the image.")
    return faces[0].normed_embedding

def process_video(learning_image_path, video_path, output_video_path, output_video_with_audio_path, socketio, flask_app):
    with flask_app.app_context():
        learning_embedding = get_face_embedding(learning_image_path).reshape(1, -1)
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            raise FileNotFoundError(f"Could not open video file: {video_path}")

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')

        if os.path.exists(output_video_path):
            os.remove(output_video_path)
            print(f"Deleted existing file: {output_video_path}")

        out = cv2.VideoWriter(output_video_path, fourcc, fps, (frame_width, frame_height))

        cosine_similarity_threshold = 0.4
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        for frame_index in tqdm(range(frame_count), desc="Processing frames", ncols=100):
            ret, frame = cap.read()
            if not ret:
                break

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            faces = app.get(rgb_frame)

            for face in faces:
                embedding = face.normed_embedding.reshape(1, -1)
                similarities = cosine_similarity(embedding, learning_embedding)
                max_similarity = similarities.max()

                x_min, y_min, x_max, y_max = face.bbox.astype(int)
                x_min = max(x_min, 0)
                y_min = max(y_min, 0)
                x_max = min(x_max, frame_width)
                y_max = min(y_max, frame_height)

                if max_similarity < cosine_similarity_threshold:
                    roi = frame[y_min:y_max, x_min:x_max].copy()
                    roi_small = cv2.resize(roi, (16, 16), interpolation=cv2.INTER_LINEAR)
                    roi_mosaic = cv2.resize(roi_small, (x_max - x_min, y_max - y_min), interpolation=cv2.INTER_NEAREST)
                    frame[y_min:y_max, x_min:x_max] = roi_mosaic

            out.write(frame)

            progress = int((frame_index + 1) / frame_count * 100)
            socketio.emit('progress', {'progress': progress})

        cap.release()
        out.release()

        combine_audio_video(video_path, output_video_path, output_video_with_audio_path, socketio, flask_app)

        socketio.emit('progress', {'progress': 100})
        print("Video processing completed.")
        cv2.destroyAllWindows()


def combine_audio_video(original_video_path, temp_video_path, output_video_path, socketio, flask_app):
    if os.path.exists(output_video_path):
        os.remove(output_video_path)
        print(f"Deleted existing file: {output_video_path}")

    original_clip = VideoFileClip(original_video_path)
    temp_clip = VideoFileClip(temp_video_path)

    audio = original_clip.audio
    final_clip = temp_clip.set_audio(audio)
    final_clip.write_videofile(output_video_path, codec='libx264', audio_codec='aac')

    # 서버의 기본 URL을 사용하여 직접 URL 생성
    complete_url = f"http://127.0.0.1:5002/gallery_convert"

    socketio.emit('complete', {'url': complete_url})

