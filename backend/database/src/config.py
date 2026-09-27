import re
from pathlib import Path

PROJECT_ROOT= Path(__file__).resolve().parents[1]

SOURCE_DIR= PROJECT_ROOT / "Intro_to_bio"
CAPTION_DIR= SOURCE_DIR / "captions"
SLIDE_DIR= SOURCE_DIR / "slides"
TRANSCRIPT_DIR= SOURCE_DIR / "transcripts"
VIDEO_DIR= SOURCE_DIR / "videos"

PROCESSED_DIR= PROJECT_ROOT / "processed"
MANIFEST_DIR= PROJECT_ROOT / "manifests"

COURSE_ID='Intro_to_bio'
COURSE_OWNER='MIT_OPENCOURSEWARE'

CAPTION_CHUNK_SIZE= 200
CAPTION_OVERLAP_SIZE= 3

VISUAL_ANALYSIS_MODEL= ["gemini-3.5-flash-lite",'gemini-3.1-flash-lite',"gemma-4-26b-a4b-it"]

unavailable_models: set[str] = set()
EMBEDDING_MODEL= "BAAI/bge-base-en-v1.5"
EMBEDDING_DIMENSIONS= 768

MAX_API_RETRIES= 3
API_RETRY_DELAY= 12 # seconds

def normalize_lecture_id(value:str)->str:
    """convert values like lec2 or lecture_02 to lec02."""
    matched = re.search(r"\d+", value)

    if not matched:
        raise ValueError(f"Invalid lecture id: {value}")

    lecture_number = int(matched.group())

    return f"lec{lecture_number:02d}"

def generate_lecture_id(lecture_id:int)->str:
    """generate lecture id from lecture number."""
    normalized_id = normalize_lecture_id(f"lec{lecture_id}")
    lecture_number = int(re.search(r"\d+", normalized_id).group())

    return {
        "lecture_id": normalized_id,
        "module_id": f"MOD_{lecture_number:02d}",
        "video_asset_id": f"VIDEO_LEC{lecture_number:02d}",
        "slide_asset_id": f"SLIDE_LEC{lecture_number:02d}",
    }

def lecture_output_dir(lecture_id:str)->Path:
    """return the processed output directory for a given lecture"""
    normalized_id = normalize_lecture_id(lecture_id)
    return PROCESSED_DIR / normalized_id