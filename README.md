# CareConnect

CareConnect is a one-stop solution for any and every need in healthcare. It comprises four main modules:

---

### **1. Hospital Assistant**

For hospital data, we have three agents:

- **Agent 1: Database Agent**
    
    Uses a Databricks-provided database. Assuming structured data is pulled from a source, it is stored and accessed here.
    
- **Agent 2: RAG Agent**
    
    Uses Retrieval-Augmented Generation with Databricks to pull insights from hospital documents containing details about branches and other minute information.
    
- **Agent 3: Internet Agent**
    
    Pulls data from the internet based on the user's location to provide real-time hospital-related information.
    

---

### **2. Pathology Assistant**

For pathology or lab data, we have two agents:

- **Agent 1: Database Agent**
    
    Uses Databricks-provided database for structured pathology/lab data storage and access.
    
- **Agent 2: Internet Agent**
    
    Pulls data from the internet based on the user's location. The goal is to help users find the nearest lab/pathology where they can get their tests done.
    

---

### **3. Medicine Assistant**

An AI agent that assists in medicine-related tasks.

If the user provides a medicine name or details, the agent searches the internet to fetch:

- Price
- Usage
- Dosage based on age
- Side effects
- Recommended duration (especially if not prescribed by a doctor)

Additionally, the agent suggests recovery advice for side effects. For example, if a fever medicine causes liver-related side effects, it may suggest consuming healthy liver-friendly fruits and vegetables after the medicine course.

---

### **4. Diagnostic Report Reader (Lab Reports, X-rays, etc.)**

This module reads pathology reports uploaded by the user and summarises the data.

Users can also upload X-rays and other diagnostic reports. The system ingests these files and provides detailed insights and summarisation.
