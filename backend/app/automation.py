import asyncio
import logging

from sqlmodel import Session, select

from app.database import engine
from app.config import get_settings
from app.models import Lead, LeadEnrichment
from app.services import enrich_lead, purge_expired_leads, run_post_event_followup, run_pre_event_cadence

logger = logging.getLogger(__name__)


def run_automation_cycle(session: Session) -> dict[str, int]:
    enriched = 0
    settings = get_settings()
    enrichments = session.exec(select(LeadEnrichment)).all()
    enriched_ids = {
        item.lead_id
        for item in enrichments
        if not (settings.enrichment_provider == "public_web" and item.source.startswith("demo:"))
    }
    for lead in session.exec(select(Lead)).all():
        if lead.id not in enriched_ids:
            enrich_lead(session, lead.id)
            enriched += 1
    pre_event = len(run_pre_event_cadence(session))
    post_event = len(run_post_event_followup(session))
    purged = purge_expired_leads(session, settings.data_retention_days)
    return {
        "enriched": enriched,
        "pre_event_messages": pre_event,
        "post_event_messages": post_event,
        "purged_leads": purged,
    }


async def automation_loop(interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            with Session(engine) as session:
                run_automation_cycle(session)
        except Exception:
            logger.exception("Automation cycle failed")
