import os

SUPPORTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']

def load_images_from_folders(folders):
    image_paths = []

    for folder in folders:
        for root, _, files in os.walk(folder):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    image_paths.append(os.path.join(root, file))

    return image_paths

def count_images_in_folder(folder):
    count = 0
    for root, _, files in os.walk(folder):
        for file in files:
            if os.path.splitext(file)[1].lower() in SUPPORTED_EXTENSIONS:
                count += 1
    return count

