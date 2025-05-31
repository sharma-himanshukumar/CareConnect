# %pip install --disable-pip-version-check -q langchain_core langchain_openai langgraph python-dotenv pymupdf python-docx
# %pip install --upgrade --force-reinstall -q databricks-vectorsearch
# %pip install --upgrade -q typing_extensions
# dbutils.library.restartPython()

import os
import sys
from typing import TypedDict, List, Annotated, Union, Dict, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers.openai_functions import PydanticOutputFunctionsParser
from langchain_core.messages import AIMessage
try:
    sys.path.append('/Workspace/Users/himanshuksharma@deloitte.com/CareConnect/careconnect')
except Exception as e:
    print(f"Error appending to sys.path: {e}")

from core.agents.hospital_service_agent import hospital_agent
from core.agents.lab_report_analysis_agent import lab_report_summarizer_agent
# from core.agents.medicine_agent import medical_recommendation_agent
from core.agents.pathology_agent import pathology_agent
DEFAULT_LOCATION = "Delhi"

class PlanStep(TypedDict, total=False):
    agent_to_call: str
    goal_for_agent: str

class OrchestratorState(TypedDict):
    original_query: str
    current_task_description: str 

    hospital_info: Optional[str]
    lab_summary_info: Optional[str]
    nearby_labs_info: Optional[str]
    drug_advice_info: Optional[str] 

    generated_plan: Optional[List[PlanStep]]
    extracted_location: Optional[str]
    extracted_symptoms: Optional[str]
    suggested_tests: Optional[List[str]] 

    final_response: str
    error_message: Optional[str]
    requires_pdf_summary: bool
    pdf_path: Optional[str]   

DATABRICKS_TOKEN = None
try:
    if 'dbutils' in globals():
        DATABRICKS_TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
        if not DATABRICKS_TOKEN: DATABRICKS_TOKEN = None
    else: print("Warning: dbutils not found.")
except Exception as e: print(f"Warning: Could not get DATABRICKS_TOKEN via dbutils ({e}).")

if DATABRICKS_TOKEN is None:
    print("CRITICAL: DATABRICKS_TOKEN is not set for Databricks LLM.")
    # DATABRICKS_TOKEN = "dummy_token_for_testing_non_llm_parts" # Uncomment to test non-LLM parts

DATABRICKS_SERVING_BASE_URL = "https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"
YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT = "databricks-claude-3-7-sonnet"

llm = None
if DATABRICKS_TOKEN and DATABRICKS_TOKEN != "dummy_token_for_testing_non_llm_parts":
    try:
        llm = ChatOpenAI(
            model_name=YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT,
            openai_api_base=DATABRICKS_SERVING_BASE_URL,
            openai_api_key=DATABRICKS_TOKEN,
            temperature=0.1,
        )
        print(f"LLM configured for Databricks: '{YOUR_DATABRICKS_MODEL_ENDPOINT_NAME_FOR_CHAT}'")
    except Exception as e: print(f"Error initializing Databricks LLM: {e}")
else: print("Databricks LLM not configured due to missing or dummy token.")

if not llm:
    print("Attempting fallback OpenAI LLM (requires OPENAI_API_KEY).")
    try:
        llm = ChatOpenAI(temperature=0.1, model_name="gpt-3.5-turbo")
        print("Initialized fallback LLM (e.g., GPT-3.5 Turbo).")
    except Exception as fallback_e:
        print(f"Error initializing fallback LLM: {fallback_e}. Planner will not work.")

class OrchestratorDecision(BaseModel):
    next_agent_direct_call: Optional[str] = Field(default=None, description="Agent to call: 'hospital_agent', 'lab_summarizer_agent', 'lab_finder_agent', 'drug_agent', or 'generate_response'.")
    plan_steps: Optional[List[PlanStep]] = Field(default=None, description="Multi-step plan. Each 'goal_for_agent' string must contain all necessary info for that agent.")
    extracted_location: Optional[str] = Field(default=None, description=f"Location from query. If none, this will be set to '{DEFAULT_LOCATION}' by the system if needed for an agent.")
    extracted_symptoms: Optional[str] = Field(default=None, description="Symptoms from query.")
    requires_pdf_summary: bool = Field(default=False, description="True if PDF summary needed.")
    pdf_path: Optional[str] = Field(default=None, description="Path to PDF (e.g., 'report.pdf').")
    reasoning: str = Field(description="Reasoning for decision.")

router_prompt_template_str = f"""
You are an expert medical query orchestrator.
The user provides a single query. Your goal is to decide the best action:
1. Call a single specialized agent directly.
2. Devise a multi-step plan if the query is complex.
3. Decide to generate a final response.

Global Default Location: '{DEFAULT_LOCATION}' (Use if no location in query AND an agent needs it).

Available agents (node names for your decision). **ALL AGENTS ACCEPT ONLY A SINGLE STRING ARGUMENT**:
- 'hospital_agent': Finds hospitals. The query string to this agent MUST include location.
    Example goal_for_agent: "Find hospitals near Delhi for heart conditions"
- 'lab_summarizer_agent': Summarizes PDF lab reports. The query string to this agent is the PDF path.
    Example goal_for_agent: "reports/my_blood_test.pdf" (You must set requires_pdf_summary=True and pdf_path from user query for this to be used)
- 'lab_finder_agent': Finds pathology labs. The query string to this agent MUST include location and any specific tests.
    Example goal_for_agent: "Find pathology labs in Mumbai for ECG and blood tests"
- 'drug_agent': Answers medicine/symptom questions, can suggest tests. Query string should be the symptom/question.
    Example goal_for_agent: "What are treatments for fever and headache?" or "Suggest tests for persistent cough."
- 'generate_response': Use when all information is gathered, or the query cannot be handled further.

User's query: "{{original_query}}"
Current context/task: "{{current_task_description}}"

Current state of collected information:
- Hospital Info: {{hospital_info}}
- Lab Summary: {{lab_summary_info}}
- Nearby Labs: {{nearby_labs_info}}
- Drug Advice (may include test suggestions from 'drug_agent'): {{drug_advice_info}}
- Suggested Tests (list, extracted by orchestrator from 'drug_agent's response): {{suggested_tests}}
- Extracted Location (from previous step, or default '{DEFAULT_LOCATION}'): {{extracted_location}}
- Extracted Symptoms (from previous step): {{extracted_symptoms}}

Decision Process:
- Analyze the user's query and the current state.
- **Location Handling**: If the user mentions a location, extract it into 'extracted_location'. If not, and an agent in your plan needs a location, you can assume '{DEFAULT_LOCATION}' for the 'goal_for_agent' string, but still set 'extracted_location' in your output to '{DEFAULT_LOCATION}' so the system knows.
- **PDF Handling**: If user mentions a PDF (e.g., "summarize report.pdf"), set 'requires_pdf_summary'=True and 'pdf_path' to the filename. The 'goal_for_agent' for 'lab_summarizer_agent' would then be just the filename.
- **Crafting 'goal_for_agent'**: THIS IS CRITICAL. For each step in 'plan_steps' (or for 'next_agent_direct_call'), the 'goal_for_agent' string must be self-contained and provide ALL information the target agent needs.
    - If 'drug_agent' suggests tests (e.g., "ECG, Blood Test"), and the next step is 'lab_finder_agent', the 'goal_for_agent' for 'lab_finder_agent' must incorporate these tests and the location. E.g., "Find labs in Delhi for ECG and Blood Test".
- If simple query for one agent: set 'next_agent_direct_call'. Construct its 'goal_for_agent' (which becomes 'current_task_description' for the agent node) to include necessary context (like location).
- If complex: define 'plan_steps'. Each step is {{ "agent_to_call": "AGENT_NODE_NAME", "goal_for_agent": "COMPLETE_QUERY_STRING_FOR_AGENT" }}.
- If done or unhandled: 'next_agent_direct_call' to 'generate_response'.
- Extract 'extracted_symptoms' if newly identified.
- Provide 'reasoning'.

IMPORTANT:
- If you create 'plan_steps', 'next_agent_direct_call' MUST be null.
- If you set 'next_agent_direct_call', 'plan_steps' MUST be null.
"""
router_prompt = ChatPromptTemplate.from_template(router_prompt_template_str)
parser = PydanticOutputFunctionsParser(pydantic_schema=OrchestratorDecision)

planner_chain = None
if llm:
    llm_with_tools = llm.bind_tools([OrchestratorDecision], tool_choice="OrchestratorDecision")
    planner_chain = router_prompt | llm_with_tools | parser
else:
    print("CRITICAL: LLM not initialized. Planner chain cannot be created.")

# --- Graph Nodes ---
def route_query_node(state: OrchestratorState):
    print(f"\n--- Router Node --- Task: {state.get('current_task_description', 'Initial Orchestration')}")
    active_plan = state.get("generated_plan")
    if active_plan:
        next_step = active_plan.pop(0)
        agent_to_call = next_step['agent_to_call']
        goal_for_agent = next_step['goal_for_agent']
        print(f"Executing plan step: Agent='{agent_to_call}', Goal='{goal_for_agent}'")
        return {
            "generated_plan": active_plan if active_plan else None,
            "next_agent": agent_to_call,
            "current_task_description": goal_for_agent,
            "extracted_location": state.get("extracted_location"),
            "extracted_symptoms": state.get("extracted_symptoms"),
            "suggested_tests": state.get("suggested_tests"),
            "requires_pdf_summary": state.get("requires_pdf_summary"),
            "pdf_path": state.get("pdf_path"),
        }

    if not planner_chain:
        return {"error_message": "Planner unavailable (LLM not initialized).", "next_agent": "generate_response", "current_task_description": "Error: LLM planner unavailable."}

    print("No active plan, calling LLM planner...")
    prompt_input = {
        "original_query": state["original_query"],
        "current_task_description": state.get("current_task_description", f"Initial query. Decide next step. Default location if needed: {DEFAULT_LOCATION}."),
        "hospital_info": state.get("hospital_info") or "Not available.",
        "lab_summary_info": state.get("lab_summary_info") or "Not available.",
        "nearby_labs_info": state.get("nearby_labs_info") or "Not available.",
        "drug_advice_info": state.get("drug_advice_info") or "Not available.",
        "suggested_tests": state.get("suggested_tests") or [],
        "extracted_location": state.get("extracted_location") or f"Not yet specified (default is {DEFAULT_LOCATION})",
        "extracted_symptoms": state.get("extracted_symptoms") or "Not specified.",
    }
    decision_obj = planner_chain.invoke(prompt_input)
    decision: Optional[OrchestratorDecision] = None
    if isinstance(decision_obj, OrchestratorDecision): decision = decision_obj
    elif isinstance(decision_obj, AIMessage) and decision_obj.tool_calls:
        try: decision = OrchestratorDecision(**decision_obj.tool_calls[0]['args'])
        except Exception as e: print(f"Error parsing planner decision: {e}")
    
    if not decision:
        return {"error_message": "Planner decision error.", "next_agent": "generate_response", "current_task_description": "Error interpreting planner output."}

    print(f"LLM Decision: {decision.reasoning}. Next: {decision.next_agent_direct_call}, Plan: {decision.plan_steps}")
    print(f"  LLM Extracted - Loc: {decision.extracted_location}, Sym: {decision.extracted_symptoms}, PDF: {decision.pdf_path if decision.requires_pdf_summary else 'No'}")

    updates = {
        "extracted_location": decision.extracted_location or state.get("extracted_location"),
        "extracted_symptoms": decision.extracted_symptoms or state.get("extracted_symptoms"),
        "requires_pdf_summary": decision.requires_pdf_summary,
        "pdf_path": decision.pdf_path,
    }
    if not updates["extracted_location"] and (
        (decision.next_agent_direct_call in ['hospital_agent', 'lab_finder_agent']) or
        (decision.plan_steps and any(step['agent_to_call'] in ['hospital_agent', 'lab_finder_agent'] for step in decision.plan_steps))
    ):
        print(f"Planner did not specify location, but it's needed. Setting extracted_location to default: {DEFAULT_LOCATION}")
        updates["extracted_location"] = DEFAULT_LOCATION


    if decision.plan_steps:
        first_goal = decision.plan_steps[0]['goal_for_agent']
        updates.update({"generated_plan": decision.plan_steps, "next_agent": "router", "current_task_description": f"Starting plan. First task: {first_goal}"})
    elif decision.next_agent_direct_call:
        effective_query_for_direct_call = state['original_query'] # Base
        if decision.extracted_location and decision.extracted_location not in effective_query_for_direct_call:
            effective_query_for_direct_call += f" (Location: {decision.extracted_location})"
        if decision.extracted_symptoms and decision.extracted_symptoms not in effective_query_for_direct_call:
            effective_query_for_direct_call += f" (Symptoms: {decision.extracted_symptoms})"


        updates.update({
            "next_agent": decision.next_agent_direct_call,
            "generated_plan": None,
            "current_task_description": effective_query_for_direct_call if decision.next_agent_direct_call != "generate_response" else "Finalizing response."
        })

    else:
        updates.update({"next_agent": "generate_response", "generated_plan": None, "current_task_description": "Finalizing response due to unclear plan."})
    return updates

def call_hospital_agent_node(state: OrchestratorState):
    print("\n--- Hospital Agent Node ---")
    query_for_agent = state.get("current_task_description", state["original_query"])
    print(f"Query for hospital_agent: '{query_for_agent}'")
    result, error_msg = f"Error: Hospital agent import/execution failed.", None
    try:
        result = hospital_agent(query_for_agent)
    except ImportError: error_msg = "ImportError: hospital_assistant_agent.hospital_agent not found."
    except Exception as e: error_msg = f"Exception in hospital_agent: {e}"
    
    if error_msg: print(f"ERROR: {error_msg}")
    updates = {"hospital_info": result, "current_task_description": f"Hospital search done."}
    if error_msg: updates["error_message"] = (state.get("error_message") or "") + f" HospitalAgent: {error_msg}; "
    return updates

def call_drug_agent_node(state: OrchestratorState):
    print("\n--- Drug/Medicine Agent Node ---")
    query_for_agent = state.get("current_task_description", state["original_query"])
    print(f"Query for medical_recommendation_agent: '{query_for_agent}'")
    result, error_msg = f"Error: Medicine agent import/execution failed.", None
    try:
        result = medical_recommendation_agent(query_for_agent)
    except ImportError: error_msg = "ImportError: medicine_agent.medical_recommendation_agent not found."
    except Exception as e: error_msg = f"Exception in medical_recommendation_agent: {e}"

    if error_msg: print(f"ERROR: {error_msg}")
    updates = {"drug_advice_info": result, "current_task_description": f"Medicine advice done."}
    
    if not error_msg and result and ("tests include" in result.lower() or "suggested tests" in result.lower()):
        try:
            tests_part_candidates = []
            if "tests include" in result.lower(): tests_part_candidates.append(result.lower().split("tests include", 1)[1])
            if "suggested tests" in result.lower(): tests_part_candidates.append(result.lower().split("suggested tests", 1)[1])
            
            tests_part = ""
            if tests_part_candidates:
                tests_part = tests_part_candidates[0].split(".")[0].strip(": ")

            if tests_part:
                raw_tests = [t.strip().capitalize() for t in tests_part.replace(" and ", ",").split(',') if t.strip()]
                if raw_tests:
                    current_tests = state.get("suggested_tests") or []
                    updated_tests = list(dict.fromkeys(current_tests + raw_tests))
                    updates["suggested_tests"] = updated_tests
                    print(f"Extracted suggested tests: {updated_tests}")
        except Exception as e: print(f"Error parsing tests from drug_advice: {e}")

    if error_msg: updates["error_message"] = (state.get("error_message") or "") + f" DrugAgent: {error_msg}; "
    return updates

def call_lab_finder_node(state: OrchestratorState):
    print("\n--- Lab Finder/Pathology Agent Node ---")
    query_for_agent = state.get("current_task_description", state["original_query"])
    print(f"Query for pathology_agent: '{query_for_agent}'")
    result, error_msg = f"Error: Pathology agent import/execution failed.", None
    try:
        result = pathology_agent(query_for_agent)
    except ImportError: error_msg = "ImportError: pathology_agent.pathology_agent not found."
    except Exception as e: error_msg = f"Exception in pathology_agent: {e}"
    
    if error_msg: print(f"ERROR: {error_msg}")
    updates = {"nearby_labs_info": result, "current_task_description": f"Lab finding done."}
    if error_msg: updates["error_message"] = (state.get("error_message") or "") + f" LabFinderAgent: {error_msg}; "
    return updates

def call_lab_summarizer_node(state: OrchestratorState):
    print("\n--- Lab Summarizer Agent Node ---")
    pdf_path_query = state.get("current_task_description")
    result, error_msg = "Error: Lab summarizer conditions not met or agent failed.", None

    if not state.get("requires_pdf_summary") or not pdf_path_query or not state.get("pdf_path"):
        error_msg = "PDF path/requirement missing or mismatched for summarizer."
        if not state.get("requires_pdf_summary"): result = "Not processed: PDF summary not marked as required by planner."
        elif not state.get("pdf_path"): result = "Not processed: PDF path not extracted by planner into state.pdf_path."
        elif not pdf_path_query: result = "Not processed: Goal for lab summarizer (PDF path) not provided in current_task_description."

    else: # All conditions met, pdf_path_query is the path
        print(f"Query for lab_report_summarizer_agent (should be PDF path): '{pdf_path_query}'")
        try:
            result = lab_report_summarizer_agent(pdf_path_query)
        except ImportError: error_msg = "ImportError: lab_report_analysis_agent.lab_report_summarizer_agent not found."
        except Exception as e: error_msg = f"Exception in lab_report_summarizer_agent: {e}"

    if error_msg: print(f"ERROR: {error_msg}")
    updates = {"lab_summary_info": result, "current_task_description": f"Lab summary done."}
    if error_msg: updates["error_message"] = (state.get("error_message") or "") + f" LabSummarizer: {error_msg}; "
    return updates

def should_continue_routing(state: OrchestratorState):
    if state.get("error_message"): return "generate_response" # Prioritize error handling
    next_node = state.get("next_agent")
    # If next_agent is None (e.g. plan just finished) or 'generate_response', go to generate_response.
    if not next_node or next_node == "generate_response":
        return "generate_response"
    return next_node # Otherwise, go to the specified agent or back to router

def generate_response_node(state: OrchestratorState):
    print("\n--- Response Generation Node ---")
    responses = []
    if state.get("error_message"): responses.append(f"Error during processing: {state['error_message']}")
    responses.append(f"Regarding your query: \"{state['original_query']}\"")

    if state.get("extracted_location"): responses.append(f"Context Location: {state['extracted_location']}.")
    if state.get("extracted_symptoms"): responses.append(f"Identified Symptoms: {state['extracted_symptoms']}.")

    if state.get("drug_advice_info"): responses.append(f"Drug/Medical Advice:\n{state['drug_advice_info']}")
    if state.get("suggested_tests"): responses.append(f"Suggested Tests: {', '.join(state['suggested_tests'])}.")
    if state.get("nearby_labs_info"): responses.append(f"Nearby Labs:\n{state['nearby_labs_info']}")
    if state.get("hospital_info"): responses.append(f"Hospitals:\n{state['hospital_info']}")
    
    lab_summary = state.get("lab_summary_info")
    if lab_summary and not any(err_kw in lab_summary for err_kw in ["Error:", "Not processed:"]):
        responses.append(f"Lab Summary:\n{lab_summary}")
    
    # Count actual info pieces, excluding query, context, and error
    info_pieces_count = sum(1 for key in ["drug_advice_info", "suggested_tests", "nearby_labs_info", "hospital_info", "lab_summary_info"]
                            if state.get(key) and not any(err_kw in str(state.get(key,"")) for err_kw in ["Error:", "Not processed:"]) )

    if not state.get("error_message") and info_pieces_count == 0:
         final_response = "\n\n".join(responses) + "\n\nI'm sorry, I couldn't gather specific actionable information for your query. Please try rephrasing or providing more details."
    elif state.get("error_message") and info_pieces_count == 0: # Error and no other info
        final_response = "\n\n".join(responses[:2]) # Show error and query context
        final_response += "\n\nI was unable to gather any further information due to the error."
    else:
        final_response = "\n\n".join(r for r in responses if r)
    
    return {"final_response": final_response, "current_task_description": "Response generated."}

# --- Graph Definition ---
from langgraph.graph import StateGraph, END

workflow = StateGraph(OrchestratorState)
workflow.add_node("router", route_query_node)
workflow.add_node("hospital_agent", call_hospital_agent_node)
workflow.add_node("lab_summarizer_agent", call_lab_summarizer_node)
workflow.add_node("lab_finder_agent", call_lab_finder_node)
workflow.add_node("drug_agent", call_drug_agent_node)
workflow.add_node("generate_response", generate_response_node)

workflow.set_entry_point("router")
workflow.add_conditional_edges("router", should_continue_routing, {
    "router": "router", "hospital_agent": "hospital_agent",
    "lab_summarizer_agent": "lab_summarizer_agent", "lab_finder_agent": "lab_finder_agent",
    "drug_agent": "drug_agent", "generate_response": "generate_response",
})
workflow.add_edge("hospital_agent", "router")
workflow.add_edge("lab_summarizer_agent", "router")
workflow.add_edge("lab_finder_agent", "router")
workflow.add_edge("drug_agent", "router")
workflow.add_edge("generate_response", END)

app = workflow.compile()

# --- Test Cases ---
# Initial state will only have 'original_query' and 'current_task_description'
def get_initial_state(query: str) -> OrchestratorState:
    return {
        "original_query": query,
        "current_task_description": "Initial user query. Orchestrator to decide first step.",
        "hospital_info": None, "lab_summary_info": None, "nearby_labs_info": None,
        "drug_advice_info": None, "generated_plan": None, "extracted_location": None,
        "extracted_symptoms": None, "suggested_tests": [], "final_response": None,
        "error_message": None, "requires_pdf_summary": False, "pdf_path": None,
    }

def run_test_case(name, query, recursion_limit=15):
    print(f"\n--- Test Case: {name} ---")
    print(f"Query: \"{query}\"")
    initial_state = get_initial_state(query)
    final_event_output = None
    
    for i, event in enumerate(app.stream(initial_state, {"recursion_limit": recursion_limit})):
        for node_name, state_after_node in event.items():
            if node_name == "__end__":
                final_event_output = state_after_node
                print(f"\nReached END state.")
                break
            print(f"Step {i+1} - Node '{node_name}':")
            print(f"  Task Description: {state_after_node.get('current_task_description')}")
            if state_after_node.get('generated_plan'): print(f"  Active Plan: {state_after_node.get('generated_plan')}")
            if state_after_node.get('extracted_location'): print(f"  Extracted Location: {state_after_node.get('extracted_location')}")
            if state_after_node.get('extracted_symptoms'): print(f"  Extracted Symptoms: {state_after_node.get('extracted_symptoms')}")
            if state_after_node.get('suggested_tests'): print(f"  Suggested Tests: {state_after_node.get('suggested_tests')}")
            if state_after_node.get('error_message'): print(f"  ERROR: {state_after_node.get('error_message')}")
        if final_event_output:
            break
            
    if final_event_output and final_event_output.get('final_response'):
        print(f"\nFinal Output for {name}:\n{final_event_output['final_response']}")
    elif final_event_output:
         print(f"\nFinal State for {name} (no final_response field or empty):\n{final_event_output}")
    else:
        print(f"\nTest Case {name} did not reach END state or had no output after {recursion_limit} steps.")
    return final_event_output

# --- Example Test Cases ---
# These assume your agent Python files are correctly imported via sys.path
# and your LLM is configured.
# If agents are not implemented, expect ImportError messages in the output.

run_test_case("Hospital query, explicit location",
              "Find hospitals for cardiac issues in Mumbai")

# run_test_case("Symptom query, no location (should use default)",
#               "I have a bad fever, what medicine should I take?")

# run_test_case("Complex query: Symptoms -> Tests -> Labs -> Hospital",
#               "I have severe chest pain and live in Bangalore. What tests should I get, where can I get them, and which hospital is good for this?")

# run_test_case("PDF summary query",
#               "Please summarize my lab report named 'my_blood_report_final.pdf'.")

# run_test_case("Lab finder for specific tests (location in query)",
#               "Where can I get an MRI and a CT scan done in Pune?")

# To visualize (optional)
# from IPython.display import Image
# try:
#     img_bytes = app.get_graph().draw_mermaid_png()
#     with open("orchestrator_graph_single_arg_agents.png", "wb") as f: f.write(img_bytes)
#     print("\nGraph saved to orchestrator_graph_single_arg_agents.png")
# except Exception as e: print(f"Could not draw graph: {e}")