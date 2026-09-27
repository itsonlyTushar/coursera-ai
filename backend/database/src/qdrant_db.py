"""Builds Qdrant points from the caption/slide/frame databases and their
embeddings, and uploads them to the collection."""

import json
import pandas as pd
from qdrant_client import QdrantClient
from qdrant_client.models import ( Distance,PointStruct,VectorParams)

from src.qdrant_common import (
    COLLECTION_NAME,
    VECTOR_DIMENSIONS,
    clean_payload_value,
    create_client as create_qdrant_client,
    create_point_id,
)
from src.database_io import DATABASE_DIR, EMBEDDING_DIR

UPLOAD_BATCH_SIZE = 100


def create_qdrant_collection(client:QdrantClient)->None:

    existing_collections = {
        collection.name
        for collection in client.get_collections().collections
    }

    if COLLECTION_NAME in existing_collections:
        print("using existing collection",COLLECTION_NAME)
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_DIMENSIONS,
            distance=Distance.COSINE,
        ),)

    print("created collection",COLLECTION_NAME)


def load_database_records(database_name:str) -> dict[str,dict]:

    database_path = DATABASE_DIR / f"{database_name}.csv"

    database_df = pd.read_csv(database_path)

    records = {}

    for record in database_df.to_dict(orient='records'):

        record_id = str(record['record_id'])

        records[record_id] = {
            key:clean_payload_value(value)
            for key,value in record.items()
        }

    return records

def load_embedding_records(database_name:str) -> list[dict]:

    embedding_path = EMBEDDING_DIR / f"{database_name}_embeddings.json"

    if not embedding_path.exists():
        raise FileNotFoundError(f"Embedding file not found: {embedding_path}")

    with open(embedding_path,"r",encoding="utf-8") as file:
        records = json.load(file)

        return records

def build_qdrant_points(database_name:str) -> list[PointStruct]:

    database_records = load_database_records(database_name)

    embedding_records = load_embedding_records(database_name)

    qdrant_points=[]

    for embedding_record in embedding_records:
        record_id = str(embedding_record['record_id'])

        if record_id not in database_records:
            raise ValueError(f"{record_id} not found in {database_name} database")


        vector = embedding_record['embedding']

        if len(vector)!=VECTOR_DIMENSIONS:
            raise ValueError(f"{record_id} has invalid embedding dimension: {len(vector)}, expected {VECTOR_DIMENSIONS}")

        payload = database_records[record_id]

        payload['embedding_model'] = embedding_record['embedding_model']

        qdrant_points.append(PointStruct(
            id=create_point_id(record_id),
            vector=vector,
            payload=payload,
        ))

    return qdrant_points

def upload_points(client:QdrantClient,points:list[PointStruct]) -> None:

    for batch_start in range(0,len(points),UPLOAD_BATCH_SIZE):

        batch = points[batch_start:batch_start+UPLOAD_BATCH_SIZE]

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch,
            wait=True,
        )
        upload_count = min(batch_start+len(batch),len(points))
        print(f"uploaded {upload_count}/{len(points)} points")


def upload_all_embeddings()->None:
    client = create_qdrant_client()

    create_qdrant_collection(client)

    database_names = [
        'caption_database',
        'slide_database',
        'frame_database',
    ]

    total_uploaded_=0

    for database_name in database_names:

        print("\n uploading:",database_name)

        points = build_qdrant_points(database_name)

        upload_points(client,points)
        total_uploaded_ += len(points)


    print('\n qdrant upload completed')
    print('collction:',COLLECTION_NAME)
    print('total records uploaded:',total_uploaded_)


if __name__ == "__main__":
    upload_all_embeddings()

    
