"""Scans the four raw-data folders and matches each video, caption, transcript,
and slide PDF by lecture number. Missing lectures (e.g. lec22) are simply absent."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.config import(
    CAPTION_DIR,
    SLIDE_DIR,
    TRANSCRIPT_DIR,
    VIDEO_DIR,
    MANIFEST_DIR,
    normalize_lecture_id,)


@dataclass(frozen=True)
class LectureAssets:
    lecture_id: str
    caption_path: Optional[Path]
    slide_path: Optional[Path]
    video_path: Optional[Path]
    transcript_path: Optional[Path]

    @property
    def is_complete(self)->bool:
        """True if video, slide, caption, and transcript are all present."""

        return all((self.video_path,
                    self.slide_path,
                    self.caption_path,
                    self.transcript_path))

    @property
    def missing_assets(self) -> list[str]:
        assets={
            'video': self.video_path,
            'slide': self.slide_path,
            'caption': self.caption_path,
            'transcript': self.transcript_path
        }
        return [name for name, path in assets.items() if not path]


def extract_lecture_id(file_path:Path) -> Optional[str]:

    matched = re.search(r"(?:lecture|lec)[_\-\s]*0*(\d+)",
                        file_path.stem,
                        flags=re.IGNORECASE)

    if not matched:
        return None

    return normalize_lecture_id(f"lec{matched.group(1)}")

def index_assets(directory:Path,extensions:set[str],) -> dict[str,Path]:
    """Index files in one asset directory by lecture_id."""
    asset_index: dict[str,Path] = {}

    for file_path in directory.rglob("*"):

        if (not file_path.is_file() or file_path.suffix.lower() not in extensions):
            continue

        lecture_id = extract_lecture_id(file_path)

        if not lecture_id:
            continue

        if lecture_id in asset_index:
            raise ValueError(f"Duplicate lecture_id {lecture_id} found in {file_path} and {asset_index[lecture_id]}")

        asset_index[lecture_id] = file_path
    return asset_index

def discover_lecture_assets() -> list[LectureAssets]:
    """Discover and match assets across all raw-data folders."""

    videos = index_assets(VIDEO_DIR, {".mp4", ".mkv", ".avi"})
    captions = index_assets(CAPTION_DIR, {".vtt", ".srt"})
    transcripts = index_assets(TRANSCRIPT_DIR, {".pdf"})
    slides = index_assets(SLIDE_DIR, {".pdf"})

    # keep lectures with only some assets so missing files show up in the inventory
    lecture_ids = sorted(
        set(videos)
        |set(captions)
        |set(transcripts)
        |set(slides),
        key=lambda value: int(re.search(r"\d+", value).group()),
    )


    return [LectureAssets(
        lecture_id=lecture_id,
        caption_path=captions.get(lecture_id),
        slide_path=slides.get(lecture_id),
        video_path=videos.get(lecture_id),
        transcript_path=transcripts.get(lecture_id),
    ) for lecture_id in lecture_ids]

def save_asset_inventory(lectures:list[LectureAssets]) -> Path:
    """Save a CSV inventory of discovered lecture assets."""

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    output_path = MANIFEST_DIR / "lecture_assets_inventory.csv"

    feilds =['lecture_id', 'video_path', 'slide_path', 'caption_path', 'transcript_path', 'status', 'missing_assets']

    with open(output_path,'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=feilds)
        writer.writeheader()

        for lecture in lectures:
            writer.writerow({
                'lecture_id': lecture.lecture_id,
                'video_path': str(lecture.video_path) if lecture.video_path else '',
                'slide_path': str(lecture.slide_path) if lecture.slide_path else '',
                'caption_path': str(lecture.caption_path) if lecture.caption_path else '',
                'transcript_path': str(lecture.transcript_path) if lecture.transcript_path else '',
                'status': 'complete' if lecture.is_complete else 'incomplete',
                'missing_assets': ', '.join(lecture.missing_assets),
            })
    return output_path



if __name__ == "__main__":
    discovered_lectures = discover_lecture_assets()
    inventory_path = save_asset_inventory(discovered_lectures)

    complete_count = sum(lecture.is_complete for lecture in discovered_lectures)
    
    print(f'lectures discovered: {len(discovered_lectures)}')
    print(f'complete lectures: {complete_count}')

    print('inventory saved to:', inventory_path)

