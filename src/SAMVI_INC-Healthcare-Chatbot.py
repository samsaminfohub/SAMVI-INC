"""
IT Support Chatbot - Streamlit Web Application
Using Claude API (Anthropic) for Healthcare IT Support

FIXED VERSION - Uses LCEL instead of legacy chains
Run with: streamlit run app_claude_fixed.py
"""

import streamlit as st
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableBranch
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyMuPDFLoader
from pathlib import Path
from dotenv import load_dotenv
import os
import shutil
import subprocess
import threading
from minio import Minio
from io import BytesIO
import tempfile
import PyPDF2
from evidently.report import Report
from evidently.metrics import ColumnSummaryMetric, DatasetSummaryMetric
from evidently.ui.workspace import Workspace
import pandas as pd
import datetime

# Load environment variables
load_dotenv()

# ============================================================================
# LANGUAGE CONFIGURATION
# ============================================================================

TRANSLATIONS = {
    "en": {
        "title": "Healthcare IT Support Chatbot",
        "welcome": "Hi! I'm your IT Support assistant. How can I help you today?",
        "clear_chat": "Clear Chat History",
        "select_language": "Select Language",
        "powered_by": "Powered by SAMVI-INC For St-Mary's Hospital",
        "feedback_thanks": "Thanks for your feedback!"
    },
    "fr": {
        "title": "Chatbot de Support IT Santé",
        "welcome": "Bonjour! Je suis votre assistant de support IT. Comment puis-je vous aider aujourd'hui?",
        "clear_chat": "Effacer l'historique du chat",
        "select_language": "Sélectionner la langue",
        "powered_by": "Propulsé par SAMVI-INC Pour Hôpital de St.Mary",
        "feedback_thanks": "Merci pour votre retour!"
    }
}

# Page configuration
st.set_page_config(
    page_title="IT Support Chatbot 🏥",
    page_icon="🏥",
    layout="wide"
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

@st.cache_resource
def load_llm(model_name="claude-sonnet-4-20250514", temperature=0.7):
    """Load and cache Claude LLM"""
    llm = ChatAnthropic(
        model=model_name,
        temperature=temperature,
        max_tokens=4096,
        timeout=None,
        max_retries=2
    )
    return llm


def extract_text_pdf(file_path):
    """Extract text from PDF file"""
    loader = PyMuPDFLoader(file_path)
    doc = loader.load()
    content = "\n".join([page.page_content for page in doc])
    return content


def config_retriever(folder_path="documents", force_rebuild=False):
    """Configure retriever - FAST mode: loads existing index, only rebuilds if needed"""
    
    index_path = "index_faiss"
    
    # FAST PATH: Load existing FAISS index FIRST (super fast!)
    if not force_rebuild and Path(index_path).exists() and Path(f"{index_path}/index.faiss").exists():
        with st.spinner("⚡ Loading existing document index..."):
            try:
                embedding_model = "BAAI/bge-large-en-v1.5"
                embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
                
                vectorstore = FAISS.load_local(
                    index_path, 
                    embeddings,
                    allow_dangerous_deserialization=True
                )
                
                retriever = vectorstore.as_retriever(
                    search_type='mmr',
                    search_kwargs={'k': 3, 'fetch_k': 4}
                )
                
                st.success("✓ Loaded existing index (instant startup!)")
                return retriever
                
            except Exception as e:
                st.warning(f"Failed to load index: {e}. Rebuilding from MinIO...")
       
    # SLOW PATH: Process PDFs directly from MinIO in memory (no disk writes)
    with st.spinner("📥 Processing PDFs from MinIO in memory..."):
        try:
            # Connect to MinIO
            minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
            minio_access = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
            minio_secret = os.getenv("MINIO_SECRET_KEY", "minioadmin")
            
            client = Minio(
                minio_endpoint,
                access_key=minio_access,
                secret_key=minio_secret,
                secure=False
            )
            
            bucket_name = "documents"
            
            # Check if bucket exists
            if not client.bucket_exists(bucket_name):
                st.error(f"❌ MinIO bucket '{bucket_name}' does not exist!")
                return None
            
            # Process PDFs in memory - no disk writes!
            objects = client.list_objects(bucket_name, recursive=True)
            objects_list = list(objects)  # Convert to list to check count
            
            st.info(f"📁 Found {len(objects_list)} file(s) in MinIO bucket '{bucket_name}'")
            
            loaded_documents = []
            pdf_count = 0
            
            for obj in objects_list:
                # Skip .dir files (DVC directory manifests)
                if obj.object_name.endswith('.dir'):
                    continue
                
                try:
                    # Download file into memory
                    response = client.get_object(bucket_name, obj.object_name)
                    file_bytes = response.read()
                    
                    # Check if file is a PDF (by magic bytes: %PDF)
                    if file_bytes.startswith(b'%PDF'):
                        # Process PDF in memory with BytesIO
                        pdf_data = BytesIO(file_bytes)
                        
                        # Extract text using PyPDF2
                        pdf_reader = PyPDF2.PdfReader(pdf_data)
                        text = ""
                        for page in pdf_reader.pages:
                            text += page.extract_text()
                        
                        if text.strip():  # Only add if we extracted text
                            loaded_documents.append(text)
                            pdf_count += 1
                            st.write(f"✓ Processed PDF: {obj.object_name} ({len(pdf_reader.pages)} pages)")
                        else:
                            st.warning(f"⚠ No text extracted from: {obj.object_name}")
                    else:
                        st.write(f"⊘ Skipped non-PDF: {obj.object_name}")
                        
                except Exception as e:
                    st.warning(f"⚠ Failed to process {obj.object_name}: {e}")
            
            if pdf_count == 0:
                st.warning(f"⚠ No valid PDF files found in MinIO bucket '{bucket_name}'")
                return None
            
            st.success(f"✓ Processed {pdf_count} PDF file(s) from MinIO in memory")
            
        except Exception as e:
            st.error(f"❌ MinIO connection error: {e}")
            st.info("Make sure MinIO is running and accessible")
            return None

    with st.spinner("📚 Building document index from extracted text..."):
        if not loaded_documents:
            st.error(f"❌ No text extracted from PDFs")
            return None

        # Split documents into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        chunks = []
        for doc in loaded_documents:
            chunks.extend(text_splitter.split_text(doc))
        
        # Create embeddings
        embedding_model = "BAAI/bge-large-en-v1.5"
        embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
        
        # Create vector store
        vectorstore = FAISS.from_texts(chunks, embedding=embeddings)
        vectorstore.save_local(index_path)
        
        # Configure retriever
        retriever = vectorstore.as_retriever(
            search_type='mmr',
            search_kwargs={'k': 3, 'fetch_k': 4}
        )
        
        st.success(f"✓ Indexed {pdf_count} documents with {len(chunks)} chunks")
        return retriever

    # FAST PATH: Load existing FAISS index if it exists (super fast!)
    if not force_rebuild and Path(index_path).exists() and Path(f"{index_path}/index.faiss").exists():
        with st.spinner("⚡ Loading existing document index (fast mode)..."):
            try:
                embedding_model = "BAAI/bge-large-en-v1.5"
                embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
                
                # Load the pre-built FAISS index
                vectorstore = FAISS.load_local(
                    index_path, 
                    embeddings,
                    allow_dangerous_deserialization=True
                )
                
                # Configure retriever
                retriever = vectorstore.as_retriever(
                    search_type='mmr',
                    search_kwargs={'k': 3, 'fetch_k': 4}
                )
                
                st.success("✓ Document index loaded (instant startup!)")
                return retriever
                
            except Exception as e:
                st.warning(f"Failed to load existing index: {e}. Rebuilding...")    
        


def format_docs(docs):
    """Format retrieved documents into a string"""
    return "\n\n".join([doc.page_content for doc in docs])


def config_rag_chain(llm, retriever):
    """Configure RAG chain using LCEL (LangChain Expression Language)"""
    
    # Contextualization prompt - reformulates question based on chat history
    contextualize_q_system_prompt = """Given a chat history and the latest user question 
    which might reference context in the chat history, formulate a standalone question 
    which can be understood without the chat history. Do NOT answer the question, 
    just reformulate it if needed and otherwise return it as is."""
    
    contextualize_q_prompt = ChatPromptTemplate.from_messages([
        ("system", contextualize_q_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    
    # Q&A system prompt
    qa_system_prompt = """You are a helpful IT Support virtual assistant for a healthcare organization.
    You provide accurate, concise answers to IT support questions.
    
    Use the following context to answer questions:
    - If the answer is in the context, provide a clear and helpful response
    - If you don't know the answer, say so honestly and suggest contacting IT support directly
    - Keep your answers professional, concise, and actionable
    - For healthcare IT systems, prioritize security and compliance in your guidance
    
    Context: {context}
    """
    
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", qa_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    
    # Create contextualized question chain
    contextualize_q_chain = contextualize_q_prompt | llm | StrOutputParser()
    
    # Function to get contextualized question or original input
    def get_contextualized_question(input_dict):
        if input_dict.get("chat_history"):
            return contextualize_q_chain.invoke(input_dict)
        return input_dict["input"]
    
    # Create the RAG chain using LCEL
    rag_chain = (
        RunnablePassthrough.assign(
            context=lambda x: format_docs(
                retriever.invoke(get_contextualized_question(x))
            )
        )
        | qa_prompt
        | llm
        | StrOutputParser()
    )
    
    return rag_chain

def log_to_evidently(user_input, response, feedback=None):
    """Background thread function for Evidently logging"""
    try:
        # Prepare data
        current_data = pd.DataFrame([
            {
                "user_input": user_input,
                "response": response,
                "timestamp": datetime.datetime.now().isoformat(),
                "input_length": len(user_input),
                "response_length": len(response),
                "feedback": feedback if feedback else "no_feedback"
            }
        ])
        
        # Log to Evidently Workspace
        try:
            workspace_path = "evidently_workspace"
            os.makedirs(workspace_path, exist_ok=True)
            
            ws = Workspace.create(workspace_path)
            
            # Create or get project
            project_name = "Chatbot Monitoring"
            project = None
            
            # Search for existing project
            search_result = ws.search_project(project_name)
            if search_result:
                project = search_result[0]
            else:
                project = ws.create_project(project_name)
                project.description = "Monitoring chatbot interactions"
            
            project.save()

            # Create report with metrics that work without reference data
            report = Report(metrics=[
                DatasetSummaryMetric(),
                ColumnSummaryMetric(column_name="user_input"),
                ColumnSummaryMetric(column_name="response"),
                ColumnSummaryMetric(column_name="input_length"),
                ColumnSummaryMetric(column_name="response_length"),
                ColumnSummaryMetric(column_name="feedback"),
            ])
            report.run(reference_data=None, current_data=current_data)
            
            # Add report to workspace
            ws.add_report(project.id, report)
            
            print(f"✓ Report added to Evidently project '{project_name}'")
            
        except Exception as report_error:
            print(f"Evidently logging failed: {report_error}")

    except Exception as e:
        print(f"Logging failed: {e}")

def chat_llm(rag_chain, user_input):
    """Process user input and update chat history"""
    
    # Get response
    response = rag_chain.invoke({
        "input": user_input,
        "chat_history": st.session_state.chat_history
    })


    
    # Update chat history
    st.session_state.chat_history.append(HumanMessage(content=user_input))
    st.session_state.chat_history.append(AIMessage(content=response))
    
# Log to Evidently (Simple logging for now)
    log_to_evidently(user_input, response)
    
    return response





# ============================================================================
# STREAMLIT UI
# ============================================================================

def main():
    # Initialize session state for language (before anything else)
    if "language" not in st.session_state:
        st.session_state.language = None
    
    # Language selection screen (show ONLY if language not selected)
    if st.session_state.language is None:
        st.markdown("<h1 style='text-align: center;'>🏥 IT Support Chatbot</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>Chatbot de Support IT</h3>", unsafe_allow_html=True)
        st.markdown("---")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.markdown("<h4 style='text-align: center;'>Select Language / Sélectionner la langue</h4>", unsafe_allow_html=True)
            st.markdown("")
            
            col_en, col_fr = st.columns(2)
            
            with col_en:
                if st.button("English", use_container_width=True, type="primary"):
                    st.session_state.language = "en"
                    st.rerun()
            
            with col_fr:
                if st.button("Français", use_container_width=True, type="primary"):
                    st.session_state.language = "fr"
                    st.rerun()
        
        return  # Stop here until language is selected
    
    # Get current language translations
    lang = st.session_state.language
    t = TRANSLATIONS[lang]
    
    # Title and description
    st.title(f"🏥 {t['title']}")
    st.markdown(f"*{t['powered_by']}*")
    
    # Sidebar
    with st.sidebar:
         #st.header("⚙️ Settings")
        
        # Language selector in sidebar
        st.markdown("---")
        current_lang = st.selectbox(
            t['select_language'],
            options=["en", "fr"],
            index=0 if lang == "en" else 1,
            format_func=lambda x: "English" if x == "en" else "Français"
        )
        
        if current_lang != st.session_state.language:
            st.session_state.language = current_lang
            st.rerun()
        
        st.markdown("---")
        
        # Force reload documents button
        # if st.button("🔄 Reload Documents (DVC)"):
        
        
        # API Key check
        #if not os.getenv("ANTHROPIC_API_KEY"):
            #st.warning("⚠️ ANTHROPIC_API_KEY not found in environment")
            #api_key = st.text_input("Enter your Anthropic API Key:", type="password")
          #  if api_key:
            #    os.environ["ANTHROPIC_API_KEY"] = api_key
        #else:
            #st.success("✓ API Key configured")
                
        # Document folder
        #doc_folder = st.text_input("Documents Folder:", value="documents")
        
         #if st.button("🔄 Reload Documents"):
          #   st.cache_resource.clear()
           #  st.rerun()

        # Clear chat button
        if st.button(f"🗑️ {t['clear_chat']}"):
            st.session_state.chat_history = []
            st.rerun()

        #st.session_state.retriever = None
        #st.cache_resource.clear()
        #st.rerun()    
                
    
    # Initialize session state
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    if "retriever" not in st.session_state:
        st.session_state.retriever = None
    
    if "llm" not in st.session_state:
        st.session_state.llm = None
    
    if "feedback_data" not in st.session_state:
        st.session_state.feedback_data = {}
    
    # Load LLM if not loaded or model changed
    current_model = "claude-sonnet-4-20250514"
    temperature = 0.7
    if st.session_state.llm is None or st.session_state.get("current_model") != current_model:
        with st.spinner("Loading Claude model..."):
            st.session_state.llm = load_llm(current_model, temperature)
            st.session_state.current_model = current_model

    
    # Display welcome message if no chat history
    if not st.session_state.chat_history:
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(t['welcome'])

    
    # Display chat history
    for idx, message in enumerate(st.session_state.chat_history):
        if isinstance(message, AIMessage):
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(message.content)
                
                # Add feedback buttons after each AI response
                col1, col2, col3 = st.columns([1, 1, 10])
                
                with col1:
                    if st.button("👍", key=f"like_{idx}"):
                        st.session_state.feedback_data[idx] = "like"
                        # Re-log to Evidently with feedback
                        if idx > 0:  # Make sure there's a user message before this
                            user_msg = st.session_state.chat_history[idx-1].content
                            log_to_evidently(user_msg, message.content, feedback="like")
                        st.rerun()
                
                with col2:
                    if st.button("👎", key=f"dislike_{idx}"):
                        st.session_state.feedback_data[idx] = "dislike"
                        # Re-log to Evidently with feedback
                        if idx > 0:  # Make sure there's a user message before this
                            user_msg = st.session_state.chat_history[idx-1].content
                            log_to_evidently(user_msg, message.content, feedback="dislike")
                        st.rerun()
                
                with col3:
                    # Show feedback status
                    if idx in st.session_state.feedback_data:
                        feedback = st.session_state.feedback_data[idx]
                        if feedback == "like":
                            st.caption(f"✅ {t['feedback_thanks']}")
                        elif feedback == "dislike":
                            st.caption(f"✅ {t['feedback_thanks']}")
                            
        elif isinstance(message, HumanMessage):
            with st.chat_message("user", avatar="👤"):
                st.markdown(message.content)
    
    # Chat input
    user_input = st.chat_input("Type your question here...")
    
    if user_input:
        # Display user message
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)
        
        # Get response
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Thinking..."):
                try:
                    # Load retriever if not loaded
                    if st.session_state.retriever is None:
                        st.session_state.retriever = config_retriever("documents")
                    
                    if st.session_state.retriever is None:
                        st.error("Failed to load documents. Please check your documents folder.")
                        return
                    
                    # Configure RAG chain
                    rag_chain = config_rag_chain(st.session_state.llm, st.session_state.retriever)
                    
                    # Get response
                    response = chat_llm(rag_chain, user_input)
                    st.markdown(response)
                    
                    # Trigger rerun to display the message with feedback buttons
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    st.info("Please make sure you have:")
                    st.markdown("""
                    1. Set your ANTHROPIC_API_KEY
                    2. Added PDF documents to the documents folder
                    3. Installed all required packages:
                       ```
                       pip install langchain langchain-anthropic langchain-community 
                       pip install langchain-huggingface langchain-text-splitters
                       pip install streamlit faiss-cpu pymupdf python-dotenv sentence-transformers
                       ```
                    """)



if __name__ == "__main__":
    main()
