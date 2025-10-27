from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class QA(Base):
    __tablename__ = 'QA'
    id = Column(Integer, primary_key=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    source = Column(String(50), default='manual')
    embedding = Column(Text, nullable=True)
    feedback = Column(String(20), default='none')
