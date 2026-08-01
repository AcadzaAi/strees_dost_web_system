"""Pre-stored distraction images for each challenge category.

Each category has a pool of 5 images stored locally in static/category_images/
Images are pre-downloaded and served directly without API calls.
"""

import random

# Category name mapping to match focus_selection options
# Each category has 5 pre-downloaded images numbered 1-5
CATEGORY_SLUGS = {
    "Phone Addiction": "phone_addiction",
    "Social Media Addiction": "social_media",
    "Entertainment Distraction": "entertainment",
    "Sports & Gaming Distraction": "gaming",
    "Exam Stress & Anxiety": "exam_stress",
    "Overthinking": "overthinking",
    "Low Motivation": "low_motivation",
    "Lack of Consistency": "lack_consistency",
    "Poor Time Management": "time_management",
    "Sleep Issues": "sleep_issues",
    "Difficulty Understanding Concepts": "understanding",
    "Low Confidence & Self-Doubt": "self_doubt",
    "Family Pressure": "family_pressure",
    "Study Burnout": "burnout",
    "Poor Concentration": "concentration"
}

# Search queries used to download images (for reference/regeneration)
CATEGORY_IMAGE_QUERIES = {
    "phone_addiction": [
        "person scrolling smartphone notifications distracted",
        "mobile phone screen glowing dark bedroom night",
        "hand holding smartphone social media apps",
        "teenager student using phone study desk",
        "smartphone addiction scrolling endlessly"
    ],
    "social_media": [
        "instagram reels endless scrolling feed",
        "social media notifications smartphone alerts",
        "youtube shorts tiktok video interface",
        "snapchat stories scrolling feed",
        "social media apps colorful icons screen"
    ],
    "entertainment": [
        "netflix binge watching streaming tv",
        "streaming service entertainment apps",
        "youtube recommendations video thumbnails",
        "tv series watching distracted studying",
        "entertainment streaming apps phone"
    ],
    "gaming": [
        "mobile gaming player intense focus",
        "playstation xbox gaming controller",
        "esports competitive gaming setup",
        "video game addiction playing late",
        "gaming console colorful screen"
    ],
    "exam_stress": [
        "student stressed worried exam papers",
        "anxiety nervous before important test",
        "clock ticking exam time pressure",
        "student overwhelmed exam preparation",
        "test anxiety worried expression"
    ],
    "overthinking": [
        "person overthinking worried anxious thoughts",
        "mind racing anxiety mental stress",
        "student stressed thinking too much",
        "mental confusion overthinking worried",
        "anxious thoughts mind overload"
    ],
    "low_motivation": [
        "student unmotivated tired studying books",
        "procrastination lazy avoiding work",
        "low energy exhausted studying desk",
        "demotivated student empty desk bored",
        "lack motivation tired burnout"
    ],
    "lack_consistency": [
        "inconsistent study messy schedule",
        "abandoned books dusty shelf neglected",
        "irregular study pattern disorganized",
        "procrastination avoiding consistent work",
        "incomplete tasks scattered notes"
    ],
    "time_management": [
        "clock time running out pressure",
        "calendar deadline approaching missed",
        "poor time management disorganized planner",
        "student rushing last minute deadline",
        "wasted time procrastination delay"
    ],
    "sleep_issues": [
        "student studying late night tired",
        "insomnia sleepless night exhausted",
        "student sleeping desk exhausted books",
        "tired yawning student studying late",
        "sleep deprivation tired studying"
    ],
    "understanding": [
        "confused student difficult math problem",
        "complex textbook hard concepts frustrated",
        "student frustrated not understanding",
        "difficult formula confused expression",
        "complex subject struggling understand"
    ],
    "self_doubt": [
        "student self doubt worried anxious",
        "imposter syndrome insecure worried student",
        "lack confidence nervous anxious",
        "self doubt fear failure exam",
        "insecure student low confidence"
    ],
    "family_pressure": [
        "parent pressure disappointed grades",
        "family expectations pressure studying",
        "disappointed parents student pressure",
        "student family expectations anxiety",
        "parental pressure academic burden"
    ],
    "burnout": [
        "student burnout exhausted overwhelmed books",
        "academic exhaustion mental fatigue tired",
        "study burnout stressed overwhelmed",
        "overwhelmed student too many books",
        "academic fatigue exhaustion burnout"
    ],
    "concentration": [
        "distracted student losing focus studying",
        "scattered attention lack concentration",
        "mind wandering daydreaming distracted",
        "poor focus concentration studying",
        "attention deficit distracted student"
    ]
}


def get_category_slug(challenge_name: str) -> str:
    """Get the slug/folder name for a challenge category."""
    return CATEGORY_SLUGS.get(challenge_name, "")


def get_local_image_paths(challenge_name: str, count: int = 5) -> list[str]:
    """Get paths to local images for a category.
    
    Args:
        challenge_name: The challenge category name
        count: Number of images to return (default 5 to get all available)
    
    Returns:
        List of relative paths to local images (e.g., 'category_images/phone_addiction_1.jpg')
        Returns ALL available images without randomization to allow caller to select unique ones
    """
    slug = get_category_slug(challenge_name)
    if not slug:
        return []
    
    # Get all 5 available images for this category
    available_images = [f"{slug}_{i}.jpg" for i in range(1, 6)]
    
    # Return all images (or up to count) without random sampling
    # This allows the caller to track and select unique images
    selected = available_images[:count]
    
    # Return relative paths (served from /static/)
    return [f"category_images/{img}" for img in selected]


def should_use_category_images(focus_selection: dict) -> bool:
    """Determine if we should use pre-defined category images.
    
    Returns True ONLY if:
    - User selected challenges AND provided NO details (completely empty/skipped)
    
    Returns False if:
    - User wrote anything at all (even 1 character) → use API images
    """
    if not focus_selection:
        return False
    
    details = focus_selection.get("details", "").strip()
    challenges = focus_selection.get("challenges", [])
    
    # If no challenges selected, don't use category images
    if not challenges:
        return False
    
    # ONLY use category images if details are COMPLETELY EMPTY
    # If user wrote ANYTHING at all, use API images
    if not details or len(details) == 0:
        return True
    
    # User provided some text (even 1 char) → use API images
    return False


__all__ = [
    "CATEGORY_SLUGS",
    "CATEGORY_IMAGE_QUERIES", 
    "get_category_slug",
    "get_local_image_paths",
    "should_use_category_images"
]
