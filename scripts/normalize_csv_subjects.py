"""
Normalize subjects and chapters in question_ids_enriched.csv to match catalog.
This ensures Chemistry questions (Organic Chemistry, Inorganic Chemistry, etc.) 
are normalized to "Chemistry" and chapter names match the catalog exactly.
"""
import csv
import json
import os

# Subject normalization mapping
SUBJECT_MAPPING = {
    "Organic Chemistry": "Chemistry",
    "Inorganic Chemistry": "Chemistry",
    "Physical Chemistry": "Chemistry",
    "Physics": "Physics",
    "Math": "Math",
    "Mathematics": "Math",
    "Biology": "Biology",
}

def load_catalog():
    """Load the acadza_catalog.json to get valid chapter names."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    catalog_path = os.path.join(project_dir, "static", "data", "acadza_catalog.json")
    
    try:
        with open(catalog_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load catalog: {e}")
        return {}

def normalize_subject(subject):
    """Normalize subject name to match catalog."""
    if not subject:
        return subject
    
    # Check exact match first
    if subject in SUBJECT_MAPPING:
        return SUBJECT_MAPPING[subject]
    
    # Check if it contains chemistry/physics/math/biology
    subject_lower = subject.lower()
    if "chemistry" in subject_lower or "chem" in subject_lower:
        return "Chemistry"
    if "physics" in subject_lower or "phy" in subject_lower:
        return "Physics"
    if "math" in subject_lower:
        return "Math"
    if "biology" in subject_lower or "bio" in subject_lower:
        return "Biology"
    
    return subject

def normalize_chapter(chapter, subject, catalog):
    """Normalize chapter name to match catalog."""
    if not chapter or not subject or subject not in catalog:
        return chapter
    
    # Get valid chapters for this subject
    valid_chapters = catalog.get(subject, {})
    
    # Check exact match (case-sensitive)
    if chapter in valid_chapters:
        return chapter
    
    # Check case-insensitive match
    chapter_lower = chapter.lower()
    for valid_chapter in valid_chapters:
        if valid_chapter.lower() == chapter_lower:
            return valid_chapter
    
    # Check if chapter is a close match (fuzzy matching)
    for valid_chapter in valid_chapters:
        # Remove common variations
        normalized_input = chapter_lower.replace("'", "'").replace("'", "'").strip()
        normalized_valid = valid_chapter.lower().replace("'", "'").replace("'", "'").strip()
        
        if normalized_input == normalized_valid:
            return valid_chapter
    
    # Return original if no match found
    return chapter

def normalize_csv(input_path, output_path=None):
    """Normalize subjects and chapters in the enriched CSV file."""
    if output_path is None:
        output_path = input_path
    
    if not os.path.exists(input_path):
        print(f"Error: File not found: {input_path}")
        return
    
    # Load catalog
    catalog = load_catalog()
    
    # Read the CSV
    rows = []
    subject_changes = 0
    chapter_changes = 0
    
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        for row in reader:
            # Normalize the subject
            original_subject = row.get('subject', '')
            normalized_subject = normalize_subject(original_subject)
            
            if original_subject != normalized_subject:
                print(f"Subject: '{original_subject}' -> '{normalized_subject}'")
                subject_changes += 1
            
            row['subject'] = normalized_subject
            
            # Normalize the chapter
            original_chapter = row.get('chapter', '')
            normalized_chapter = normalize_chapter(original_chapter, normalized_subject, catalog)
            
            if original_chapter != normalized_chapter:
                print(f"Chapter: '{original_chapter}' -> '{normalized_chapter}' (in {normalized_subject})")
                chapter_changes += 1
            
            row['chapter'] = normalized_chapter
            rows.append(row)
    
    # Write back to CSV
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\n✓ Processed {len(rows)} questions")
    print(f"✓ Normalized {subject_changes} subjects")
    print(f"✓ Normalized {chapter_changes} chapters")
    print(f"✓ Output written to: {output_path}")

if __name__ == "__main__":
    # Get the path to the enriched CSV
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    csv_path = os.path.join(project_dir, "data", "question_ids_enriched.csv")
    
    print(f"Normalizing subjects and chapters in: {csv_path}\n")
    normalize_csv(csv_path)
