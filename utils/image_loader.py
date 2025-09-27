import os

SUPPORTED_IMAGE_FORMATS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')

def get_all_images_from_folders(folders):
    image_paths = []
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for root, _, files in os.walk(folder):
            for file in sorted(files):
                if file.lower().endswith(SUPPORTED_IMAGE_FORMATS):
                    image_paths.append(os.path.join(root, file))
    return image_paths
