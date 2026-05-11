"""
Incidental Findings Follow-up Agent
RAG pipeline over clinical documents using LangChain, AWS Bedrock, and DynamoDB.
Extracts, classifies, and routes incidental findings with urgency scoring.
"""

import json
import re
import boto3
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_aws import BedrockEmbeddings, ChatBedrock
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BEDROCK_REGION = "us-east-1"
EMBEDDING_MODEL = "amazon.titan-embed-text-v1"
LLM_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"
DYNAMODB_TABLE = "clinical-findings-index"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
TOP_K_RETRIEVAL = 5

URGENCY_THRESHOLDS = {
    "URGENT": 7,    # days
    "SOON": 30,
    "ROUTINE": 90,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ClinicalDocument:
    doc_id: str
    patient_id: str          # de-identified
    modality: str            # CT, MRI, X-Ray, etc.
    body_region: str
    report_text: str
    report_date: str
    location_id: str

@dataclass
class Finding:
    description: str
    urgency: str             # URGENT | SOON | ROUTINE
    timeframe: str
    action: str
    icd10_codes: list[str]
    guideline_citation: str
    confidence: float        # 0–1, triggers human review queue if < 0.75

@dataclass
class TriageResult:
    doc_id: str
    patient_id: str
    findings: list[Finding]
    summary: str
    routed_to: str           # scheduling system, radiologist queue, etc.
    requires_human_review: bool


# ---------------------------------------------------------------------------
# DynamoDB index — stores document metadata and finding records
# ---------------------------------------------------------------------------

class FindingsIndex:
    def __init__(self):
        self.dynamo = boto3.resource("dynamodb", region_name=BEDROCK_REGION)
        self.table = self.dynamo.Table(DYNAMODB_TABLE)

    def put_document(self, doc: ClinicalDocument):
        self.table.put_item(Item={
            "pk": f"DOC#{doc.doc_id}",
            "sk": "METADATA",
            "patient_id": doc.patient_id,
            "modality": doc.modality,
            "body_region": doc.body_region,
            "report_date": doc.report_date,
            "location_id": doc.location_id,
            "status": "PENDING",
        })

    def put_findings(self, doc_id: str, findings: list[Finding]):
        for i, f in enumerate(findings):
            self.table.put_item(Item={
                "pk": f"DOC#{doc_id}",
                "sk": f"FINDING#{i:03d}",
                "description": f.description,
                "urgency": f.urgency,
                "timeframe": f.timeframe,
                "action": f.action,
                "icd10_codes": f.icd10_codes,
                "guideline_citation": f.guideline_citation,
                "confidence": str(f.confidence),
                "requires_review": f.confidence < 0.75,
            })

    def get_pending_documents(self, location_id: str) -> list[dict]:
        response = self.table.query(
            IndexName="location-status-index",
            KeyConditionExpression="location_id = :loc AND #s = :status",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":loc": location_id, ":status": "PENDING"},
        )
        return response.get("Items", [])


# ---------------------------------------------------------------------------
# Embedding + retrieval layer
# ---------------------------------------------------------------------------

class GuidelineRetriever:
    def __init__(self, opensearch_endpoint: str):
        self.embeddings = BedrockEmbeddings(
            model_id=EMBEDDING_MODEL,
            region_name=BEDROCK_REGION,
        )
        self.vectorstore = OpenSearchVectorSearch(
            opensearch_url=opensearch_endpoint,
            index_name="clinical-guidelines",
            embedding_function=self.embeddings,
        )

    def retrieve(self, query: str, k: int = TOP_K_RETRIEVAL) -> list[dict]:
        docs = self.vectorstore.similarity_search_with_relevance_scores(query, k=k)
        return [
            {"content": doc.page_content, "metadata": doc.metadata, "score": score}
            for doc, score in docs
            if score > 0.65
        ]

    @classmethod
    def index_guidelines(cls, guidelines: list[dict], opensearch_endpoint: str):
        """One-time indexing of clinical guideline corpus."""
        embeddings = BedrockEmbeddings(model_id=EMBEDDING_MODEL, region_name=BEDROCK_REGION)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        texts, metadatas = [], []
        for g in guidelines:
            chunks = splitter.split_text(g["body"])
            texts.extend(chunks)
            metadatas.extend([{
                "guideline_id": g["id"],
                "title": g["title"],
                "source": g["source"],
            }] * len(chunks))
        OpenSearchVectorSearch.from_texts(
            texts=texts,
            metadatas=metadatas,
            embedding=embeddings,
            opensearch_url=opensearch_endpoint,
            index_name="clinical-guidelines",
        )


# ---------------------------------------------------------------------------
# Extraction + classification chain
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a clinical findings triage agent. Given a radiology or clinical
report and retrieved guidelines, extract incidental findings requiring follow-up.

Return valid JSON only:
{{
  "findings": [
    {{
      "description": "concise finding (max 15 words)",
      "urgency": "URGENT|SOON|ROUTINE",
      "timeframe": "specific timeframe e.g. 3 months",
      "action": "specific follow-up action (max 20 words)",
      "icd10_codes": ["Z87.39"],
      "guideline_citation": "guideline id or 'none'",
      "confidence": 0.0-1.0
    }}
  ],
  "summary": "one sentence summary of overall incidental finding burden"
}}

Urgency: URGENT = within 7 days, SOON = within 30 days, ROUTINE = beyond 30 days.
Only include findings requiring follow-up. Exclude primary reason for study."""),
    ("human", "RETRIEVED GUIDELINES:\n{context}\n\n---\n\nREPORT:\n{report}"),
])

def build_rag_chain(retriever: GuidelineRetriever):
    llm = ChatBedrock(
        model_id=LLM_MODEL,
        region_name=BEDROCK_REGION,
        model_kwargs={"max_tokens": 1500, "temperature": 0.1},
    )

    def format_context(docs: list[dict]) -> str:
        return "\n\n".join(
            f"[{d['metadata']['guideline_id']}] {d['metadata']['title']}\n{d['content']}"
            for d in docs
        )

    return (
        {
            "context": lambda x: format_context(retriever.retrieve(x["report"])),
            "report": RunnablePassthrough() | (lambda x: x["report"]),
        }
        | EXTRACTION_PROMPT
        | llm
        | StrOutputParser()
    )


# ---------------------------------------------------------------------------
# HIPAA guardrails
# ---------------------------------------------------------------------------

PHI_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN REDACTED]"),
    (r"\b(?:0[1-9]|1[0-2])[/-]\d{2}[/-]\d{4}\b", "[DOB REDACTED]"),
    (r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", "[NAME REDACTED]"),
    (r"\(\d{3}\) \d{3}-\d{4}", "[PHONE REDACTED]"),
    (r"\b\d{5}(?:-\d{4})?\b", "[ZIP REDACTED]"),
]

def redact_phi(text: str) -> str:
    for pattern, replacement in PHI_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


# ---------------------------------------------------------------------------
# Routing layer
# ---------------------------------------------------------------------------

def route_finding(finding: Finding, location_id: str) -> str:
    if finding.urgency == "URGENT":
        return f"radiologist-review-queue/{location_id}/urgent"
    elif finding.urgency == "SOON":
        return f"scheduling-system/{location_id}/priority"
    else:
        return f"scheduling-system/{location_id}/routine"


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

class FindingsAgent:
    def __init__(self, opensearch_endpoint: str):
        self.retriever = GuidelineRetriever(opensearch_endpoint)
        self.chain = build_rag_chain(self.retriever)
        self.index = FindingsIndex()

    def process(self, doc: ClinicalDocument) -> TriageResult:
        # Redact PHI before LLM processing
        safe_text = redact_phi(doc.report_text)

        # RAG extraction
        raw_output = self.chain.invoke({"report": safe_text})
        cleaned = raw_output.strip().lstrip("```json").rstrip("```").strip()
        parsed = json.loads(cleaned)

        findings = [
            Finding(
                description=f["description"],
                urgency=f["urgency"],
                timeframe=f["timeframe"],
                action=f["action"],
                icd10_codes=f.get("icd10_codes", []),
                guideline_citation=f["guideline_citation"],
                confidence=float(f.get("confidence", 0.8)),
            )
            for f in parsed.get("findings", [])
        ]

        requires_review = any(f.confidence < 0.75 for f in findings)
        routed_to = route_finding(findings[0], doc.location_id) if findings else "no-action"

        self.index.put_document(doc)
        self.index.put_findings(doc.doc_id, findings)

        return TriageResult(
            doc_id=doc.doc_id,
            patient_id=doc.patient_id,
            findings=findings,
            summary=parsed.get("summary", ""),
            routed_to=routed_to,
            requires_human_review=requires_review,
        )


# ---------------------------------------------------------------------------
# FastAPI interface
# ---------------------------------------------------------------------------

app = FastAPI()

class DocumentRequest(BaseModel):
    doc_id: str
    patient_id: str
    modality: str
    body_region: str
    report_text: str
    report_date: str
    location_id: str

@app.post("/analyze")
def analyze_document(req: DocumentRequest, opensearch_endpoint: str = "https://localhost:9200"):
    agent = FindingsAgent(opensearch_endpoint)
    doc = ClinicalDocument(**req.dict())
    try:
        result = agent.process(doc)
        return {
            "doc_id": result.doc_id,
            "findings_count": len(result.findings),
            "findings": [
                {
                    "description": f.description,
                    "urgency": f.urgency,
                    "timeframe": f.timeframe,
                    "action": f.action,
                    "confidence": f.confidence,
                }
                for f in result.findings
            ],
            "summary": result.summary,
            "requires_human_review": result.requires_human_review,
            "routed_to": result.routed_to,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    sample_doc = ClinicalDocument(
        doc_id=hashlib.md5(b"sample").hexdigest(),
        patient_id="PT-REDACTED-001",
        modality="CT",
        body_region="Abdomen/Pelvis",
        report_text="""CT ABDOMEN AND PELVIS WITH CONTRAST
        FINDINGS: 1.3 cm hypodense lesion in hepatic segment VI. 9 mm pulmonary
        nodule right lower lobe. 4 mm non-obstructing left renal calculus.
        T11 vertebral compression deformity, chronicity unclear.
        IMPRESSION: Incidental findings as above requiring follow-up per guidelines.""",
        report_date="2025-03-14",
        location_id="LOC-001",
    )
    print(f"Document ID: {sample_doc.doc_id}")
    print(f"PHI-redacted excerpt: {redact_phi(sample_doc.report_text[:80])}")
    print("Agent initialized — requires AWS Bedrock and OpenSearch credentials to run.")
