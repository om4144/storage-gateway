from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel, create_engine, Session
from app.services.cleanup_schedular import start_cleanup_task

sqlite_filename = "metadata.db"
sqlite_url = f"sqlite:///{sqlite_filename}"

# print sql query's in the terminal
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)

@asynccontextmanager
async def lifespan(app: FastAPI):
  # Automatically creates tables if they don't exist yet
  SQLModel.metadata.create_all(engine)

  # Start the background cleanup scheduler
  start_cleanup_task(engine)

  # --- APP STARTUP EVENT ---
  print("Database tables initialized successfully.")
  
  yield 
  
  # --- APP SHUTDOWN MESSAGE ---
  print("Application is shutting down. Database resources freed.")

def get_session():
  with Session(engine) as session:
    yield session