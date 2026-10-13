from PIL import ImageDraw, ImageFont, Image
from .utils import tensor2pil, pil2tensor, tensor2Mask
import math
import os

FONT_DIR = os.path.join(os.path.dirname(__file__),"fonts")

class AddSubtitlesToFramesNode:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": { 
                "images": ("IMAGE",),
                "alignment" : ("whisper_alignment",),
                "font_color": ("STRING",{
                    "default": "white"
                }),
                "font_border_color": ("STRING", {
                    "default": "black"
                }),
                "font_border_width": ("INT", {
                    "default": 4,
                    "step": 1,
                    "display": "number"
                }),
                "font_family": (os.listdir(FONT_DIR),),
                "font_size": ("INT",{
                    "default": 100,
                    "step":5,
                    "display": "number"
                }),
                "x_position": ("INT",{
                    "default": 100,
                    "step":50,
                    "display": "number"
                }),
                "y_position": ("INT",{
                    "default": 100,
                    "step":50,
                    "display": "number"
                }),
                "center_x": ("BOOLEAN", {"default": True}),
                "center_y": ("BOOLEAN", {"default": False}), # Defaulted to False for layout logic
                "video_fps": ("FLOAT",{
                    "default": 24.0,
                    "step":1,
                    "display": "number"
                }),
                "linger_threshold": ("FLOAT", {
                    "default": 3.0,
                    "min": 0.0,
                    "max": 10.0,
                    "step": 0.1,
                    "display": "number"
                }),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "IMAGE", "subtitle_coord", )
    RETURN_NAMES = ("IMAGE","MASK", "cropped_subtitles","subtitle_coord",)
    FUNCTION = "add_subtitles_to_frames"
    CATEGORY = "whisper"

    def add_subtitles_to_frames(self, images, alignment, font_family, font_size, font_color, x_position, y_position, center_x, center_y, video_fps, font_border_color, font_border_width, linger_threshold):
        pil_images = tensor2pil(images)

        pil_images_with_text = []
        cropped_pil_images_with_text = []
        pil_images_masks = []
        subtitle_coord = []

        font = ImageFont.truetype(os.path.join(FONT_DIR,font_family), font_size)

        if len(alignment) == 0:
            pil_images_with_text = pil_images
            cropped_pil_images_with_text = pil_images
            subtitle_coord.extend([(0,0,0,0)]*len(pil_images))

            width, height = pil_images[0].size
            black_img = Image.new('RGB', (width, height), 'black')
            pil_images_masks.extend([black_img]*len(pil_images))
            
            tensor_images = pil2tensor(pil_images_with_text)
            cropped_tensor_images = pil2tensor(cropped_pil_images_with_text)
            tensor_masks = tensor2Mask(pil2tensor(pil_images_masks))
            return (tensor_images, tensor_masks, cropped_tensor_images, subtitle_coord,)
        
        last_frame_no = 0
        for i in range(len(alignment)):
            alignment_obj = alignment[i]
            
            start_frame_no = math.floor(alignment_obj["start"] * video_fps)
            
            # Universal Fix: Calculate dynamic end time to hold text on screen longer
            raw_end = alignment_obj["end"]
            if i < len(alignment) - 1:
                next_start = alignment[i+1]["start"]
                if next_start - raw_end < linger_threshold:
                    end_frame_no = math.floor(next_start * video_fps)
                else:
                    end_frame_no = math.floor(raw_end * video_fps)
            else:
                end_frame_no = min(math.floor((raw_end + (linger_threshold / 2)) * video_fps), len(pil_images))

            # Safety adjustments
            if start_frame_no < last_frame_no:
                start_frame_no = last_frame_no
            if end_frame_no <= start_frame_no:
                end_frame_no = start_frame_no + 1
            if end_frame_no > len(pil_images):
                end_frame_no = len(pil_images)

            # Draw blank gaps
            for j in range(last_frame_no, start_frame_no):
                img = pil_images[j].convert("RGB")
                width, height = img.size
                pil_images_with_text.append(img)

                black_img = Image.new('RGB', (width, height), 'black')
                pil_images_masks.append(black_img)
                black_img = Image.new('RGB', (1, 1), 'black') 
                cropped_pil_images_with_text.append(black_img)  
                subtitle_coord.append((0,0,0,0))

            # Render frames for active block
            for k in range(start_frame_no, end_frame_no):
                img = pil_images[k].convert("RGB")
                width, height = img.size

                d = ImageDraw.Draw(img)

                # DYNAMIC MULTI-LINE WORD WRAPPING
                raw_text = alignment_obj["value"]
                max_chars = 25  
                
                words = raw_text.split()
                lines = []
                current_line = ""
                
                for word in words:
                    test_line = f"{current_line} {word}".strip() if current_line else word
                    if len(test_line) <= max_chars:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
                
                text = "\n".join(lines)

                current_x = x_position
                current_y = y_position

                # 1. First, get standard bounding box at an arbitrary position to calculate total text height
                temp_bbox = d.textbbox((0, 0), text, font=font, align="center")
                text_width = temp_bbox[2] - temp_bbox[0]
                text_height = temp_bbox[3] - temp_bbox[1]

                # 2. Horizontal centering logic
                if center_x:
                    current_x = (width - text_width) / 2

                # 3. VERTICAL BOTTOM-UP ALIGNMENT LOGIC
                if center_y:
                    # Fallback to middle of the screen if center_y toggle is True
                    current_y = (height - text_height) / 2
                else:
                    # Treat the user's 'y_position' input slider as the baseline (the bottom boundary).
                    # We subtract the dynamic total height of the text block to expand upward.
                    current_y = y_position - text_height

                # Draw border outlines
                for dx in range(-font_border_width, font_border_width + 1):
                    for dy in range(-font_border_width, font_border_width + 1):
                        if dx != 0 or dy != 0:
                            d.text((current_x + dx, current_y + dy), text, fill=font_border_color, font=font, align="center")

                # Draw main text
                d.text((current_x, current_y), text, fill=font_color, font=font, align="center")
                pil_images_with_text.append(img)

                # Create mask
                black_img = Image.new('RGB', (width, height), 'black')
                d_mask = ImageDraw.Draw(black_img)

                for dx in range(-font_border_width, font_border_width + 1):
                    for dy in range(-font_border_width, font_border_width + 1):
                        d_mask.text((current_x + dx, current_y + dy), text, fill="white", font=font, align="center")

                d_mask.text((current_x, current_y), text, fill="white", font=font, align="center")
                pil_images_masks.append(black_img)    

                # Crop boundaries
                text_bbox = d_mask.textbbox((current_x, current_y), text, font=font, align="center")
                text_bbox = (
                    text_bbox[0] - font_border_width,
                    text_bbox[1] - font_border_width,
                    text_bbox[2] + font_border_width,
                    text_bbox[3] + font_border_width,
                )
                cropped_text_frame = black_img.crop(text_bbox)
                cropped_pil_images_with_text.append(cropped_text_frame)
                subtitle_coord.append(text_bbox)
            
            last_frame_no = end_frame_no

        # Fill remaining frames
        for m in range(len(pil_images_with_text), len(pil_images)):
            pil_images_with_text.append(pil_images[m])
            width, height = pil_images[m].size

            black_img = Image.new('RGB', (width, height), 'black')
            pil_images_masks.append(black_img)
            black_img = Image.new('RGB', (1, 1), 'black') 
            cropped_pil_images_with_text.append(black_img)  
            subtitle_coord.append((0,0,0,0))

        # Size normalization
        cropped_pil_images_with_text_normalised = []
        max_width = max(img.width for img in cropped_pil_images_with_text)
        max_height = max(img.height for img in cropped_pil_images_with_text)

        for img in cropped_pil_images_with_text:
            blank_frame = Image.new("RGB", (max_width, max_height), "black")
            blank_frame.paste(img, (0,0))
            cropped_pil_images_with_text_normalised.append(blank_frame)

        tensor_images = pil2tensor(pil_images_with_text)
        cropped_tensor_images = pil2tensor(cropped_pil_images_with_text_normalised)
        tensor_masks = tensor2Mask(pil2tensor(pil_images_masks))

        return (tensor_images, tensor_masks, cropped_tensor_images, subtitle_coord,)
