# %pip install --disable-pip-version-check -q langchain_core langchain_openai langgraph pymupdf python-docx

# dbutils.library.restartPython()

import os
import sys
import fitz
import json
from docx import Document 
from typing import TypedDict, Annotated, List, Union, TypedDict, Optional, Annotated
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from openai import OpenAI
sys.path.append('/Workspace/Users/himanshuksharma@deloitte.com/CareConnect/careconnect')

class AgentState(TypedDict):
    uploaded_file: Optional[str]
    file_path: Optional[str]
    raw_lab_text: Optional[str]
    cleaned_lab_data: Optional[str]
    lab_summary: Optional[str]
    final_answer: Optional[str]
    error_message: Optional[str] 

try:
    DATABRICKS_TOKEN = os.getenv('DATABRICKS_TOKEN') ##dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    if not DATABRICKS_TOKEN:
        raise ValueError("DATABRICKS_TOKEN is not set.")
except Exception as e:
    print(f"Error getting DATABRICKS_TOKEN: {e}. Please ensure it's correctly configured.")
    DATABRICKS_TOKEN = "dummy_token_if_testing_non_llm_parts"

DATABRICKS_SERVING_BASE_URL = "https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"
YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT = "databricks-claude-3-7-sonnet"
try:
    llm = ChatOpenAI(
        model_name=YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT,
        openai_api_base=DATABRICKS_SERVING_BASE_URL, 
        openai_api_key=DATABRICKS_TOKEN,
        temperature=0.1, 
    )
    print(f"LangChain LLM (ChatOpenAI) configured for Databricks Model Serving endpoint: '{YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT}' at '{DATABRICKS_SERVING_BASE_URL}'")
except Exception as e:
    print(f"Error initializing ChatOpenAI for Databricks Model Serving. Ensure endpoint name and token are correct. Error: {e}")


def file_uploader_node(state: AgentState) -> AgentState:
    print("---EXECUTING FILE UPLOADER NODE---")
    file = state.get("uploaded_file")
    if not file:
        return {"error_message": "No file uploaded."}
    if not os.path.exists(file):
        return {"error_message": f"File not found at path: {file}"}
    return {"file_path": file, "error_message": None}

def file_extractor_node(state: AgentState) -> AgentState:
    print("---EXECUTING FILE EXTRACTOR NODE---")
    if state.get("error_message"): 
        return {}
    file_path = state.get("file_path")
    if not file_path:
        return {"error_message": "File path not provided to extractor."}

    try:
        text = ""
        if file_path.endswith(".pdf"):
            doc = fitz.open(file_path)
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()
        elif file_path.endswith(".docx"):
            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)
        else:
            return {"error_message": "Unsupported file format. Only .pdf and .docx are supported."}
        
        if not text.strip():
            return {"error_message": "No text could be extracted from the file."}
        return {"raw_lab_text": text, "error_message": None}
    except Exception as e:
        return {"error_message": f"File extraction error: {str(e)}"}

def lab_report_cleaner_node(state: AgentState) -> AgentState:
    print("---EXECUTING LAB REPORT CLEANER NODE---")
    if state.get("error_message"):
        return {}
    raw_text = state.get("raw_lab_text", "")
    if not raw_text:
        return {"error_message": "No text extracted from lab report to clean."}

    cleaned_text = raw_text.replace('\n\n', '\n').replace('  ', ' ').strip()
    cleaned_text = "\n".join([line.strip() for line in cleaned_text.split('\n') if line.strip()])

    print(f"Cleaned text preview (first 500 chars):\n{cleaned_text[:500]}")
    return {"cleaned_lab_data": cleaned_text, "error_message": None}

def lab_summary_node(state: AgentState) -> AgentState:
    print("---EXECUTING LAB SUMMARY NODE---")
    if state.get("error_message"):
        return {}
    cleaned_data = state.get("cleaned_lab_data", "")
    if not cleaned_data:
        return {"error_message": "No cleaned lab data to summarize."}

    prompt = f"""
    You are an expert medical assistant AI. A patient has uploaded their lab report.
    Here is the extracted and cleaned data from their lab report:

    <lab_report_data>
    {cleaned_data}
    </lab_report_data>

    Your task is to analyze this lab report data and provide a summary for the patient.
    Please explain the findings in simple, clear, non-technical language that a layperson can easily understand.
    For each significant test or group of tests mentioned:
    1. Briefly explain what the test is for (its purpose).
    2. Indicate whether the result appears to be within a normal range, high, or low. If reference ranges are provided in the text, use them. If not, use general medical knowledge.
    3. Explain the potential implications of any abnormal results in simple terms.
    4. Explicitly state if a result needs medical attention or follow-up with a doctor.

    Structure your summary clearly. Be concise but informative. Avoid medical jargon where possible, or explain it if unavoidable.
    If the provided data is insufficient or seems corrupted for a comprehensive analysis, please state that.
    Do not provide medical advice or diagnosis, but rather explain the report and suggest when to consult a healthcare professional.
    Start your response with a general overview and then go into specifics.
    """
    try:
        response = llm.invoke(prompt)
        return {"lab_summary": response.content, "error_message": None}
    except Exception as e:
        return {"error_message": f"LLM summarization failed: {str(e)}"}

def lab_final_response_node(state: AgentState) -> AgentState:
    print("---EXECUTING FINAL RESPONSE NODE---")
    if state.get("error_message"):
        return {"final_answer": f"Could not complete analysis. Error: {state['error_message']}"}
    
    summary = state.get("lab_summary")
    if not summary:
        return {"final_answer": "No summary was generated. There might have been an issue in a previous step."}
    return {"final_answer": summary}

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("file_uploader", file_uploader_node)
workflow.add_node("file_extractor", file_extractor_node)
workflow.add_node("lab_cleaner", lab_report_cleaner_node)
workflow.add_node("lab_summarizer", lab_summary_node)
workflow.add_node("responder", lab_final_response_node)

# Set entry and edges
workflow.set_entry_point("file_uploader")
workflow.add_edge("file_uploader", "file_extractor")
workflow.add_edge("file_extractor", "lab_cleaner")
workflow.add_edge("lab_cleaner", "lab_summarizer")
workflow.add_edge("lab_summarizer", "responder")
workflow.add_edge("responder", END)

app = workflow.compile()

def lab_report_summarizer_agent(user_query: str, file_path_to_analyze: str):
    inputs = {"uploaded_file": file_path_to_analyze}
    final_state = None
    final_state = app.invoke(inputs)
    # for event in app.stream(inputs, {"recursion_limit": 10}):
    #     for key, value in event.items():
    #         print(f"---EVENT FROM NODE: {key}---")
    #         if 'error_message' in value and value['error_message']:
    #             print(f"ERROR: {value['error_message']}")
    #         if 'final_answer' in value:
    #             final_state = value
    
    if final_state and final_state.get("final_answer"):
        return final_state["final_answer"]
    elif final_state and final_state.get("error_message"):
        return f"Analysis failed. Error: {final_state.get('error_message')}"
    return "No response generated, and no specific error reported in final state."


if __name__ == "__main__":
    # %pip install --disable-pip-version-check -q langchain_core langchain_openai langgraph pymupdf python-docx
    # dbutils.library.restartPython()
    print("\n--- Analyzing PDF Report ---")
    file ="/Volumes/careconnect/default/lab_reports/CBC-test-report-format-example-sample-template-Drlogy-lab-report.pdf"
    if os.path.exists(file):
        pdf_report_path = file
        pdf_summary = lab_report_summarizer_agent("asdasda",pdf_report_path)
        print("\nFINAL PDF SUMMARY:\n", pdf_summary)
    else:
        print("dummy_lab_report.pdf not found, skipping PDF analysis.")



