"""Non-secret engine identity captured when the analysis modules load.

Report downloads carry this ID so a stale hosted worker can be distinguished from
an analysis defect. No document contents or user information enter the hash.
"""
from hashlib import sha256
from pathlib import Path

ENGINE_RELEASE='Acquisition Intelligence 5 - validation'
_ENGINE_FILES=('legal_pack_engine.py','acquisition_lease_evidence.py','acquisition_property_evidence.py','acquisition_document.py','legal_pack_ingest.py','legal_pack_review.py','legal_pack_service.py','acquisition_chronology.py','acquisition_intelligence.py','acquisition_report.py','acquisition_amendments.py','acquisition_energy.py','acquisition_evidence_graph.py','acquisition_investigation.py','acquisition_market_evidence.py','acquisition_presentation.py','acquisition_premium.py','acquisition_quality.py','acquisition_reasoning.py','acquisition_transcription.py')
_root=Path(__file__).resolve().parent
ENGINE_BUILD=sha256(b''.join(name.encode()+b'\0'+(_root/name).read_bytes() for name in _ENGINE_FILES)).hexdigest()[:12]

def engine_identity():
    return {'release':ENGINE_RELEASE,'build':ENGINE_BUILD}
