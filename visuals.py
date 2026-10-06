import os
import aiohttp
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

async def create_moodboard(image_sources: list, output_path: str = "collage.jpg") -> str:
    """
    Creates a 2x2 collage from up to 4 image sources.
    Sources can be URLs (http/https) or local file paths.
    Returns the file path of the generated collage.
    """
    if not image_sources:
        return ""
        
    images = []
    
    for source in image_sources[:4]:
        try:
            if source.startswith("http://") or source.startswith("https://"):
                # Download from URL
                async with aiohttp.ClientSession() as session:
                    async with session.get(source) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            img = Image.open(io.BytesIO(data))
                            images.append(img)
            elif os.path.exists(source):
                # Load from local file
                img = Image.open(source)
                images.append(img)
        except Exception as e:
            logger.error(f"Failed to load image {source}: {e}")
                
    if not images:
        return ""
        
    # Resize all to 300x300
    target_size = (300, 300)
    resized_images = [img.resize(target_size, Image.Resampling.LANCZOS) for img in images]
    
    # Create grid based on number of images
    cols = 2 if len(resized_images) > 1 else 1
    rows = (len(resized_images) + 1) // 2
    
    collage = Image.new('RGB', (target_size[0] * cols, target_size[1] * rows), (255, 255, 255))
    
    positions = [
        (0, 0), (target_size[0], 0),
        (0, target_size[1]), (target_size[0], target_size[1])
    ]
    
    for i, img in enumerate(resized_images):
        if i < len(positions):
            collage.paste(img, positions[i])
            
    collage.save(output_path, "JPEG")
    return output_path
