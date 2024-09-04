import os
import boto3
import streamlit as st
from langchain_aws import BedrockEmbeddings
from langchain_aws.chat_models import ChatBedrock
from langchain_community.vectorstores.faiss import FAISS
from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders.pdf import PyPDFDirectoryLoader
from langchain.globals import set_verbose
set_verbose(False)

bedrock = boto3.client(service_name='bedrock-runtime', region_name='us-east-1')
titan_embeddings = BedrockEmbeddings(model_id="amazon.titan-embed-text-v1", client=bedrock)

# Data Preparation
def data_ingestion():
    loader = PyPDFDirectoryLoader("data")
    documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=500)
    docs = text_splitter.split_documents(documents)
    return docs

# Vector Store Setup
def setup_vector_store(documents):
    vector_store = FAISS.from_documents(
        documents,
        titan_embeddings,
    )
    vector_store.save_local("faiss_index")

# LLM Setup
def load_llm():
    llm = ChatBedrock(model_id="anthropic.claude-3-5-sonnet-20240620-v1:0", client=bedrock, model_kwargs={"max_tokens": 2048})
    return llm

# LLM Guidelines
prompt_template = """Use the following pieces of context to answer the question at the end. Follow these rules:
1. If the answer is not within the context knowledge, state that you do not know, versus fabricating a response.
2. If you find the answer, please craft a detailed, thorough, and concise response to the question at the end. Aim for a summary of max 250 words.

{context}

Question: {question}
Helpful Answer:"""

# Prompt Template
prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])

# Create QA Chain 
def get_result(llm, vector_store, query):
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vector_store.as_retriever(
            search_type="similarity", search_kwargs={"k": 3}
        ),
        chain_type_kwargs={"prompt": prompt},
        return_source_documents=True,
    )
    # Apply LLM
    result = qa_chain.invoke(query)
    return result['result']

# Streamlit Frontend UI Section
def streamlit_ui():
    st.set_page_config("RAG")
    st.markdown("""
        <style>
            .reportview-container {
                margin-top: -2em;
            }
            #MainMenu {visibility: hidden;}
            .stDeployButton {display:none;}
            footer {visibility: hidden;}
            #stDecoration {display:none;}
        </style>
    """, unsafe_allow_html=True)
    st.header("PDF Query with Generative AI")

    user_question = st.text_input("Ask me anything about your PDF collection.")

    left_column, middleleft_column, middleright_column, right_column = st.columns(4, gap="small")
    if left_column.button("Generate Response", key="submit_question") or user_question:
        # first check if the vector store exists
        if not os.path.exists("faiss_index"):
            st.error("Please create the vector store first from the sidebar.")
            return
        if not user_question:
            st.error("Please enter a question.")
            return
        with st.spinner("Generating... this may take a minute..."):
            faiss_index = FAISS.load_local("faiss_index", embeddings=titan_embeddings,
                                           allow_dangerous_deserialization=True)
            llm = load_llm()
            st.write(get_result(llm, faiss_index, user_question))
            st.success("Generated")
    if right_column.button("New Data Update", key="update_vector_store"):
        with st.spinner("Updating... this may take a few minutes as we go through your PDF collection..."):
            docs = data_ingestion()
            setup_vector_store(docs)
            st.success("Updated")

if __name__ == "__main__":
    streamlit_ui()
