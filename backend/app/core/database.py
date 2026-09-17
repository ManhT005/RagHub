import os
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Text, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
DATA = Path(os.getenv("RAGHUB_DATA", "data"))
DATA.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DATA / 'raghub.db'}", connect_args={"check_same_thread": False})
Session = sessionmaker(engine)
Base = declarative_base()
class Record(Base):
    __tablename__ = "records"
    id = Column(String, primary_key=True)
    kind = Column(String, index=True, nullable=False)
    owner = Column(String, index=True, nullable=False)
    parent = Column(String, index=True, default="")
    payload = Column(Text, nullable=False)
class Token(Base):
    __tablename__ = "tokens"
    digest = Column(String, primary_key=True)
    owner = Column(String, nullable=False)
    expires = Column(Integer, nullable=False)
Base.metadata.create_all(engine)
