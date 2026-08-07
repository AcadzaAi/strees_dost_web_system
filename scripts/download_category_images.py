"""Script to pre-download category images for all 15 challenge categories.

This downloads 5 images for each category and saves them to static/category_images/
Total: 75 images (15 categories × 5 images)

Usage:
    py -3.12 scripts/download_category_images.py
"""

import os
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.category_images import CATEGORY_SLUGS, CATEGORY_IMAGE_QUERIES
from app.api.trigger_routes import _openai_find_candidate_urls, _download_pool, _vision_rank_images

def download_images_for_category(slug: str, queries: list[str], output_dir: Path):
    """Download 5 images for a category."""
    print(f"\n{'='*60}")
    print(f"Processing category: {slug}")
    print(f"{'='*60}")
    
    for idx, query in enumerate(queries, 1):
        output_file = output_dir / f"{slug}_{idx}.jpg"
        
        if output_file.exists():
            print(f"  [{idx}/5] ✓ Already exists: {output_file.name}")
            continue
        
        print(f"  [{idx}/5] Searching: '{query}'")
        
        try:
            # Create intent object
            intent = {
                "subject": query,
                "image_query": query,
                "kind": "photo"
            }
            
            # Find candidate URLs
            candidate_urls = _openai_find_candidate_urls(intent)
            if not candidate_urls:
                print(f"  [{idx}/5] ✗ No URLs found")
                continue
            
            print(f"  [{idx}/5]   Found {len(candidate_urls)} candidates, downloading...")
            
            # Download images
            downloaded = _download_pool(candidate_urls)
            if not downloaded:
                print(f"  [{idx}/5] ✗ No valid images downloaded")
                continue
            
            print(f"  [{idx}/5]   Downloaded {len(downloaded)} images, ranking...")
            
            # Rank by relevance
            try:
                best_ids = _vision_rank_images(query, downloaded)
                if best_ids and best_ids[0]:
                    img_id = best_ids[0]
                else:
                    img_id = downloaded[0][0]
            except Exception:
                # If vision ranking fails, use first image
                img_id = downloaded[0][0]
            
            # Find the image data
            img_data = None
            for d_id, data, ctype in downloaded:
                if d_id == img_id:
                    img_data = data
                    break
            
            if not img_data:
                img_data = downloaded[0][1]  # Fallback to first image
            
            # Save to file
            with open(output_file, "wb") as f:
                f.write(img_data)
            
            print(f"  [{idx}/5] ✓ Saved: {output_file.name}")
            
            # Rate limit to avoid API throttling
            time.sleep(2)
            
        except Exception as e:
            print(f"  [{idx}/5] ✗ Error: {e}")
            continue


def main():
    # Setup output directory
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    output_dir = project_dir / "static" / "category_images"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("="*60)
    print("CATEGORY IMAGE DOWNLOADER")
    print("="*60)
    print(f"Output directory: {output_dir}")
    print(f"Total categories: {len(CATEGORY_SLUGS)}")
    print(f"Images per category: 5")
    print(f"Total images to download: {len(CATEGORY_SLUGS) * 5}")
    print("="*60)
    
    # Download images for each category
    for category_name, slug in CATEGORY_SLUGS.items():
        queries = CATEGORY_IMAGE_QUERIES.get(slug, [])
        if not queries:
            print(f"\n⚠ No queries found for {slug}")
            continue
        
        download_images_for_category(slug, queries, output_dir)
    
    print("\n" + "="*60)
    print("DOWNLOAD COMPLETE!")
    print("="*60)
    
    # Count downloaded files
    downloaded_files = list(output_dir.glob("*.jpg"))
    print(f"Total images downloaded: {len(downloaded_files)}")
    print(f"Location: {output_dir}")


if __name__ == "__main__":
    main()
