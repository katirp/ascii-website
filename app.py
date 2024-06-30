from flask import Flask, request, send_from_directory, redirect, url_for, render_template_string, jsonify
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps
import math
import cv2
from moviepy.editor import ImageSequenceClip
import numpy as np
import shutil
import re
import subprocess

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
ASCII_FRAMES_FOLDER = 'asciiframes'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['ASCII_FRAMES_FOLDER'] = ASCII_FRAMES_FOLDER
og_fps = None


def ensure_and_clear_directory(directory):
    # Create the directory if it does not exist
    os.makedirs(directory, exist_ok=True)
    
    # Clear all items in the directory
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

@app.route('/')
def upload_form():
    return render_template_string('''
    <!doctype html>
    <html lang="en"> 
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
        <title>Video Upload</title>
        <link rel="stylesheet" type = "text/css" href= "{{ url_for('static',filename='app.css') }}">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Pixelify+Sans:wght@400..700&display=swap" rel="stylesheet">
      </head>
      <body>
      <div class="page">     
            <h1 id="title" class="text">ascii and you shall receive</h1>
            <p class="text">upload a video file</p>
            <form method="post" action="/upload" enctype="multipart/form-data" >
                <input type="file" name="file" accept="video/mp4,video/quicktime" id="file-input" class="file-input">
                <label for="file-input" class="rounded-button custom-file-label">Choose File</label>
                <input type="submit" value="Upload" class="rounded-button">
            </form>
            <span id="loading" class="file-name" style="display:none;">Loading...</span>
            <span id="file-name" class="file-name"></span> <!-- Added span for file name -->
        </div>
        <script>
            document.getElementById('file-input').addEventListener('change', function(event) {
                var fileName = event.target.files[0].name;
                document.getElementById('file-name').textContent = fileName;
            });
                    
        </script>
      </body>
    </html>
    ''')

@app.route('/upload', methods=['POST'])
def upload_file():
    # Ensure and clear the directories
    ensure_and_clear_directory(UPLOAD_FOLDER)
    ensure_and_clear_directory(PROCESSED_FOLDER)
    ensure_and_clear_directory(ASCII_FRAMES_FOLDER)
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Please select a file'}), 400
    if file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        processed_file_path = process_video(file_path)
        formatted_file_path = format_path(processed_file_path)
        return redirect(url_for('download_file', filename=os.path.basename(formatted_file_path)))

@app.route('/processed/<filename>')
def download_file(filename):
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename, as_attachment=True)

def extract_frames(video_path):
    cam = cv2.VideoCapture(video_path)
    global og_fps 
    og_fps = cam.get(cv2.CAP_PROP_FPS)
    current_frame = 0
    frame_paths = []

    while True:
        ret, frame = cam.read()
        if ret:
            frame_path = os.path.join(app.config['UPLOAD_FOLDER'], f"frame{current_frame}.jpg")
            cv2.imwrite(frame_path, frame)
            frame_paths.append(frame_path)
            current_frame += 1
        else:
            break

    cam.release()
    return frame_paths

def asciify_image(image_path, output_path):
    im1 = Image.open(image_path)
    im2 = ImageOps.grayscale(im1)

    width, height = im2.size
    desired_res = 10000
    scale_factor = (desired_res / (width * height)) ** 0.5
    im = im2.resize((math.ceil(width * scale_factor), math.ceil(height * scale_factor)))

    pixel_vals = list(im.getdata())
    ascii_chars = ["@", "%", "#", "*", "+", "=", "-", ":", ".", " "]

    step = (max(pixel_vals) - min(pixel_vals)) // len(ascii_chars)

    ascii_image = ""
    row_counter = 0

    for pixel in pixel_vals:
        index = pixel // step
        if index >= len(ascii_chars):
            index = len(ascii_chars) - 1
        character = ascii_chars[index]
        ascii_image += character + " "
        row_counter += 1
        if row_counter >= width * scale_factor:
            ascii_image += "\n"
            row_counter = 0

    with open(output_path, 'w') as f:
        f.write(ascii_image)

def folder_to_ascii(directory, output_directory):
    frame_paths = []
    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".jpg"):
            file_path = os.path.join(directory, filename)
            output_path = os.path.join(output_directory, filename.replace(".jpg", ".txt"))
            asciify_image(file_path, output_path)
            frame_paths.append(output_path)
    return frame_paths

def numerical_sort(value):
    # Extract the numerical part from the frame name using regex
    numbers = re.findall(r'\d+', value)
    return int(numbers[0]) if numbers else 0

def ascii_frames_to_video(ascii_frame_paths, output_path):
    # this is originally lexicographical order, so numerically sort by using numerical_sort
    ascii_frame_paths.sort(key=numerical_sort)

    frames = []
    for ascii_frame_path in ascii_frame_paths:
        with open(ascii_frame_path, 'r') as f:
            content = f.read()

        #move the width and height calculation out
        print("drawing frames to video", ascii_frame_path)
        lines = content.split('\n')
        width = max(len(line) for line in lines)
        height = len(lines)
    
        # Create an image with white background
        image = Image.new('L', (width * 7, height * 17), color=255)
        # image = Image.new('L', (target_size[1], target_size[0]), color=255)
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("Monaco.ttf", 13)  # Adjust the size as needed
        except IOError:
            print("Specified monospaced font file not found. Using default font.")
            font = ImageFont.load_default()  # Fallback to default font if specified font is not found

        # Draw text onto the image
        draw.text((0, 0), content, font=font, fill=0)

        # Convert the image to a numpy array
        image_np = np.array(image)
        frames.append(image_np)

    # Find the maximum dimensions
    max_height = max(frame.shape[0] for frame in frames)
    max_width = max(frame.shape[1] for frame in frames)

    # Resize all frames to the maximum dimensions
    resized_frames = []
    for frame in frames:
        frame_pil = Image.fromarray(frame)
        frame_resized = ImageOps.pad(frame_pil, (max_width, max_height), method=Image.BILINEAR)
        resized_frames.append(np.array(frame_resized))

    # Create a video clip from the frames. The first line layers the frames 3 times because even when the video is grayscale video players expect RGB format
    clip = ImageSequenceClip([np.stack([frame]*3, axis=-1) for frame in frames], fps=og_fps)
    clip.write_videofile(output_path, codec='libx264', audio_codec='aac')

# Quicktime player has trouble playing the original processed video sometimes, due to formatting issues. This function reformats the video using ffmpeg.
def format_path(input_path):
    # Create a temporary file for the output
    output_path = os.path.join(app.config['PROCESSED_FOLDER'], 'formatted_video.mp4')
    # FFmpeg command to re-encode the video
    ffmpeg_command = [
        'ffmpeg',
        '-i', input_path,
        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
        '-c:v', 'libx264',
        '-profile:v', 'high',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'copy',
        output_path
    ]
    # Run the FFmpeg command
    subprocess.run(ffmpeg_command, check=True)
    return output_path
   

def process_video(input_path):
    frame_paths = extract_frames(input_path)
    ascii_frame_paths = folder_to_ascii(os.path.dirname(frame_paths[0]), app.config['ASCII_FRAMES_FOLDER'])
    output_path = os.path.join(app.config['PROCESSED_FOLDER'], 'processed_video.mp4')
    ascii_frames_to_video(ascii_frame_paths, output_path)
    return output_path

if __name__ == '__main__':
    app.run(debug=True)
