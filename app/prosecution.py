"""Prosecution Case Builder - Evidence chains, timelines, confidence scoring

This module structures investigation data into prosecution-ready format:
- Timeline events with confidence scores
- Target profiles with evidence chains
- Witness/victim tracking
- Source corroboration and conflicts
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json
from app.db import execute_query

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TimelineEvent:
    """A dated event in the investigation timeline"""
    date: str                    # ISO date or "YYYY-MM" or "YYYY"
    date_precision: str          # "day", "month", "year", "approximate"
    event: str                   # What happened
    category: str                # "trafficking", "financial", "legal", "travel", "meeting"
    targets_involved: List[str]  # People involved
    confidence: int              # 0-100%
    source_ids: List[int]        # Document IDs that support this
    source_count: int            # Number of corroborating sources
    conflicts: List[str]         # Any conflicting information
    notes: str                   # Additional context

@dataclass
class EvidenceItem:
    """A piece of evidence against a target"""
    doc_id: int
    doc_title: str
    evidence_type: str           # "document", "testimony", "financial", "witness"
    summary: str                 # What this evidence shows
    confidence: int              # How reliable (0-100)
    date_of_evidence: str        # When the evidence is from
    corroborated_by: List[int]   # Other doc IDs that support this

@dataclass
class ProsecutionTarget:
    """A person who could face prosecution"""
    name: str
    aliases: List[str]
    potential_charges: List[str]
    status: str                  # "under investigation", "charged", "convicted", "settled"
    evidence_chain: List[EvidenceItem]
    witnesses: List[str]         # People who could testify against them
    timeline_events: List[str]   # References to timeline events
    confidence_score: int        # Overall prosecution readiness (0-100)
    last_updated: str

# =============================================================================
# PROSECUTION TARGETS DATABASE
# =============================================================================

# GUILT FLAG SCALE:
# -2: Cleared / Confirmed victim
# -1: Likely victim or wrongly accused
#  0: No evidence of wrongdoing
#  1-2: Association only, no criminal evidence
#  3-4: Suspicious involvement, enabled
#  5-6: Credible accusations, evidence mounting
#  7-8: Strong evidence, likely guilty
#  9-10: Overwhelming evidence, should be prosecuted
# 11-12: Convicted / Confirmed guilty

PROSECUTION_TARGETS_DB = {
    'ghislaine_maxwell': {
        'name': 'Ghislaine Maxwell',
        'aliases': ['G-Max', 'GM'],
        'potential_charges': ['Sex trafficking of minors', 'Conspiracy', 'Perjury'],
        'status': 'Convicted (2021) - 20 years',
        'guilt_flag': 12,  # CONVICTED - 20 years federal prison
        'flag_reason': 'Convicted on 5 counts of sex trafficking. FBI tracked her to Manchester-by-Sea. Managed $600M+ criminal enterprise with Epstein.',
        'key_evidence': [
            {'type': 'testimony', 'summary': 'Multiple victims testified to her recruitment role', 'confidence': 95},
            {'type': 'document', 'summary': 'Flight logs show extensive travel with Epstein', 'confidence': 95},
            {'type': 'testimony', 'summary': 'Participated directly in abuse per victims', 'confidence': 85},
            {'type': 'fbi', 'summary': 'FBI tracked her location via Boston office before arrest', 'confidence': 100},
            {'type': 'fbi', 'summary': 'EFTA00037453: FBI emails show surveillance coordination pre-arrest', 'confidence': 100},
            {'type': 'financial', 'summary': '$600M+ estate - VI AG alleges tax programs funded trafficking', 'confidence': 90},
            {'type': 'document', 'summary': '1996 victim affidavit: "school-age girls" seen at Epstein mansion', 'confidence': 85},
            {'type': 'witness', 'summary': 'Witnesses withdrew cooperation citing safety fears', 'confidence': 80},
        ],
        'witnesses': ['Virginia Giuffre', 'Annie Farmer', 'Kate', 'Jane', 'Carolyn', 'UK-based witnesses'],
        'confidence_score': 98,
    },
    'jean_luc_brunel': {
        'name': 'Jean-Luc Brunel',
        'aliases': [],
        'potential_charges': ['Sex trafficking', 'Rape of minors'],
        'status': 'Died in custody (2022) - apparent suicide',
        'guilt_flag': 10,  # Would have been convicted - died before trial
        'flag_reason': 'Charged with rape of minors, trafficking. Multiple accusers. Died in custody before trial.',
        'key_evidence': [
            {'type': 'testimony', 'summary': 'Multiple models accused him of rape/drugging', 'confidence': 85},
            {'type': 'document', 'summary': 'MC2 agency used to recruit for Epstein', 'confidence': 90},
            {'type': 'testimony', 'summary': 'Virginia Giuffre named him as abuser', 'confidence': 80},
        ],
        'witnesses': ['Virginia Giuffre', 'Multiple models'],
        'confidence_score': 78,
    },
    'prince_andrew': {
        'name': 'Prince Andrew',
        'aliases': ['Duke of York', 'Andrew Windsor'],
        'potential_charges': ['Sexual abuse of a minor', 'Sex trafficking conspiracy'],
        'status': 'Settled civil lawsuit (2022)',
        'guilt_flag': 8,  # Strong evidence - paid $12M+ to settle, stripped of titles
        'flag_reason': 'Photo evidence, victim testimony, paid $12M+ settlement, stripped of royal titles. Epstein pleaded 5th on ALL questions about Andrew. FBI found 21 document mentions.',
        'key_evidence': [
            {'type': 'testimony', 'summary': 'Virginia Giuffre testified she was trafficked to him 3 times', 'confidence': 85},
            {'type': 'photograph', 'summary': 'Photo with Giuffre at Maxwell London home', 'confidence': 95},
            {'type': 'flight_log', 'summary': 'Multiple flights on Epstein aircraft', 'confidence': 90},
            {'type': 'witness', 'summary': 'Staff testimony about visits to Epstein properties', 'confidence': 75},
            {'type': 'deposition', 'summary': 'Epstein pleaded 5th on ALL questions regarding Prince Andrew', 'confidence': 100},
            {'type': 'document', 'summary': '21 FOIA document mentions found - flight logs, victim accounts', 'confidence': 90},
            {'type': 'fbi', 'summary': 'FBI coordinated with UK NCA on London-based witness interviews', 'confidence': 85},
        ],
        'witnesses': ['Virginia Giuffre', 'Johanna Sjoberg', 'Epstein staff', 'UK-based witnesses (FBI coordination)'],
        'confidence_score': 85,
    },
    'alexander_acosta': {
        'name': 'Alexander Acosta',
        'aliases': [],
        'potential_charges': ['Corrupt plea deal', 'Obstruction of justice', 'Victims rights violations'],
        'status': 'Resigned as Labor Secretary (2019)',
        'guilt_flag': 8,  # Upgraded: DOJ OPR Report found "poor judgment", 60-count indictment reduced
        'flag_reason': 'DOJ OPR Report confirmed 60-count federal indictment was reduced to 18-month state plea. Violated CVRA. Used "professional judgment" defense. Protected predator.',
        'key_evidence': [
            {'type': 'legal', 'summary': 'Negotiated lenient 2008 plea deal', 'confidence': 100},
            {'type': 'document', 'summary': 'Deal violated victims rights laws', 'confidence': 95},
            {'type': 'testimony', 'summary': 'Claimed told Epstein was intelligence', 'confidence': 60},
            {'type': 'doj_report', 'summary': 'DOJ OPR: 60-count federal indictment reduced to 18-month state plea', 'confidence': 100},
            {'type': 'doj_report', 'summary': 'DOJ OPR found Acosta "used poor judgment" but no prosecution', 'confidence': 100},
            {'type': 'document', 'summary': 'EFTA00011475: Full OPR Executive Summary in FOIA files', 'confidence': 100},
            {'type': 'legal', 'summary': 'Victims not notified as required by CVRA - federal judge ruled deal illegal', 'confidence': 95},
        ],
        'witnesses': ['Julie K. Brown (reporter)', 'Victims', 'DOJ OPR investigators'],
        'confidence_score': 78,
    },
    'alan_dershowitz': {
        'name': 'Alan Dershowitz',
        'aliases': [],
        'potential_charges': ['Sexual abuse allegations', 'Corrupt plea deal participation'],
        'status': 'Denies all allegations',
        'guilt_flag': 6,  # Upgraded: Epstein pleaded 5th on Dershowitz + minors questions
        'flag_reason': 'Epstein pleaded 5th when asked about minors at Dershowitz house. Helped negotiate corrupt NPA. 20 FOIA document mentions. Denies everything.',
        'key_evidence': [
            {'type': 'testimony', 'summary': 'Virginia Giuffre accused him of abuse', 'confidence': 70},
            {'type': 'document', 'summary': 'Flight logs show travel on Epstein jet', 'confidence': 90},
            {'type': 'legal', 'summary': 'Was part of 2008 plea deal legal team', 'confidence': 100},
            {'type': 'deposition', 'summary': 'Epstein pleaded 5th when asked about minors at Dershowitz house', 'confidence': 95},
            {'type': 'document', 'summary': '20 FOIA document mentions in deposition searches', 'confidence': 90},
            {'type': 'legal', 'summary': 'Key architect of NPA that protected co-conspirators', 'confidence': 85},
        ],
        'witnesses': ['Virginia Giuffre', 'Deposition transcripts'],
        'confidence_score': 62,
    },
    'les_wexner': {
        'name': 'Les Wexner',
        'aliases': ['Leslie Wexner'],
        'potential_charges': ['Financial enablement', 'Suspicious property transfer'],
        'status': 'Not charged - claims victim of fraud',
        'guilt_flag': 4,  # Major enabler - gave him everything, claims ignorance
        'flag_reason': 'Gave Epstein power of attorney, $77M mansion, legitimacy. Claims he was defrauded. Enabled the operation.',
        'key_evidence': [
            {'type': 'financial', 'summary': 'Gave Epstein power of attorney over finances', 'confidence': 100},
            {'type': 'property', 'summary': 'Transferred $77M NYC mansion to Epstein', 'confidence': 100},
            {'type': 'document', 'summary': 'Long financial relationship documented', 'confidence': 95},
        ],
        'witnesses': [],
        'confidence_score': 60,
    },
    'bill_gates': {
        'name': 'Bill Gates',
        'aliases': ['William Gates III'],
        'potential_charges': ['Association with convicted felon'],
        'status': 'Admitted meetings - claims regret',
        'guilt_flag': 2,  # Association only - met him AFTER conviction, bad judgment
        'flag_reason': 'Met Epstein multiple times AFTER 2008 conviction. Flew on his jet. No abuse allegations. Bad judgment.',
        'key_evidence': [
            {'type': 'document', 'summary': 'Multiple meetings after 2008 conviction', 'confidence': 100},
            {'type': 'email', 'summary': 'Email correspondence documented', 'confidence': 95},
            {'type': 'travel', 'summary': 'Flew on Epstein jet at least once', 'confidence': 85},
            {'type': 'financial', 'summary': 'Donation discussions documented', 'confidence': 80},
        ],
        'witnesses': [],
        'confidence_score': 45,
    },
    'sarah_kellen': {
        'name': 'Sarah Kellen',
        'aliases': ['Sarah Kensington', 'Sarah Vickers'],
        'potential_charges': ['Sex trafficking conspiracy', 'Recruiting minors', 'Maintaining surveillance databases'],
        'status': 'Named in NPA - granted immunity',
        'guilt_flag': 9,  # Should be prosecuted - was scheduler/recruiter with surveillance role
        'flag_reason': '160 FOIA document mentions. Maintained surveillance database of victims with photos/contact info. Named co-conspirator. Granted immunity.',
        'key_evidence': [
            {'type': 'document', 'summary': 'Named as potential co-conspirator in 2008 NPA', 'confidence': 100},
            {'type': 'testimony', 'summary': 'Multiple victims described her recruiting role', 'confidence': 90},
            {'type': 'document', 'summary': 'Message pads show her scheduling "massages"', 'confidence': 95},
            {'type': 'testimony', 'summary': 'Described as primary scheduler of victims', 'confidence': 85},
            {'type': 'deposition', 'summary': '160 mentions in FOIA documents - most of any assistant', 'confidence': 100},
            {'type': 'document', 'summary': 'Maintained database with victim names, photos, contact info', 'confidence': 90},
            {'type': 'testimony', 'summary': 'Victims describe her as "gatekeeper" who knew everything', 'confidence': 85},
        ],
        'witnesses': ['Virginia Giuffre', 'Courtney Wild', 'Multiple Jane Does', 'Deposition transcripts'],
        'confidence_score': 88,
    },
    'nadia_marcinkova': {
        'name': 'Nadia Marcinkova',
        'aliases': ['Nadia Marcinko', 'Global Girl'],
        'potential_charges': ['Sex trafficking', 'Sexual abuse of minors'],
        'status': 'Named in NPA - granted immunity',
        'guilt_flag': 7,  # Complicated - was victim first, then participant
        'flag_reason': 'Allegedly brought to US as teenager by Epstein. Later participated in abuse per victims. Complex victim-turned-abuser situation.',
        'key_evidence': [
            {'type': 'document', 'summary': 'Named as potential co-conspirator in 2008 NPA', 'confidence': 100},
            {'type': 'testimony', 'summary': 'Victims described her participating in abuse', 'confidence': 80},
            {'type': 'document', 'summary': 'Described as "Yugoslavian sex slave" in police report', 'confidence': 90},
            {'type': 'testimony', 'summary': 'Virginia Giuffre described threesome situations', 'confidence': 75},
        ],
        'witnesses': ['Virginia Giuffre', 'Jane Does'],
        'confidence_score': 70,
    },
    'leon_black': {
        'name': 'Leon Black',
        'aliases': [],
        'potential_charges': ['Sexual assault allegations', 'Financial ties to trafficking'],
        'status': 'Stepped down from Apollo - denies wrongdoing',
        'guilt_flag': 6,  # Paid Epstein $158M (!), allegations
        'flag_reason': 'Paid Epstein $158 MILLION in fees. Guzel Ganieva allegations. Stepped down from Apollo. Claims financial advice only.',
        'key_evidence': [
            {'type': 'financial', 'summary': 'Paid Epstein $158M over years for "advice"', 'confidence': 100},
            {'type': 'testimony', 'summary': 'Guzel Ganieva alleges rape, assault', 'confidence': 70},
            {'type': 'document', 'summary': 'Apollo internal review found "poor judgment"', 'confidence': 95},
            {'type': 'travel', 'summary': 'Visited Epstein properties documented', 'confidence': 80},
        ],
        'witnesses': ['Guzel Ganieva'],
        'confidence_score': 62,
    },
    'jes_staley': {
        'name': 'Jes Staley',
        'aliases': ['James Staley'],
        'potential_charges': ['Concealing relationship with sex trafficker'],
        'status': 'Resigned from Barclays (2021)',
        'guilt_flag': 5,  # Lied about relationship, 1200+ emails
        'flag_reason': 'Exchanged 1200+ emails with Epstein. Visited him in prison. Lied to Barclays. Forced to resign. No direct abuse allegations.',
        'key_evidence': [
            {'type': 'document', 'summary': '1200+ emails with Epstein over years', 'confidence': 100},
            {'type': 'document', 'summary': 'Visited Epstein in Florida jail (2008)', 'confidence': 100},
            {'type': 'document', 'summary': 'Sailed to Epstein island on his yacht', 'confidence': 90},
            {'type': 'testimony', 'summary': 'Barclays found he misrepresented relationship', 'confidence': 95},
        ],
        'witnesses': [],
        'confidence_score': 55,
    },
    'bill_clinton': {
        'name': 'Bill Clinton',
        'aliases': ['William Jefferson Clinton', '42nd President'],
        'potential_charges': ['Association under investigation', 'Witness credibility issues'],
        'status': 'Denies close relationship',
        'guilt_flag': 5,  # Upgraded: Pilot deposition "10-20 times", ditched Secret Service
        'flag_reason': 'Pilot Larry Visoski testified Clinton was on plane "ten or twenty times". Flight logs show 26+ trips. Flew without Secret Service. Giuffre saw him on island.',
        'key_evidence': [
            {'type': 'flight_log', 'summary': 'Documented on Epstein flights 26+ times', 'confidence': 90},
            {'type': 'testimony', 'summary': 'Giuffre says she saw him on island', 'confidence': 60},
            {'type': 'document', 'summary': 'Denies ever visiting island', 'confidence': 50},
            {'type': 'photograph', 'summary': 'Photos with Ghislaine Maxwell', 'confidence': 95},
            {'type': 'deposition', 'summary': 'Pilot Larry Visoski: Clinton on plane "ten or twenty times"', 'confidence': 95},
            {'type': 'deposition', 'summary': 'Flew without Secret Service on some flights per logs', 'confidence': 85},
            {'type': 'testimony', 'summary': 'Chauntae Davies (masseuse) confirms Clinton flights', 'confidence': 80},
        ],
        'witnesses': ['Virginia Giuffre (saw on island)', 'Flight crew', 'Larry Visoski (pilot)', 'Chauntae Davies'],
        'confidence_score': 58,
    },
    'donald_trump': {
        'name': 'Donald Trump',
        'aliases': ['45th President'],
        'potential_charges': ['Historical association', 'Mar-a-Lago venue exploitation'],
        'status': 'Distanced himself - claims he banned Epstein',
        'guilt_flag': 4,  # Upgraded: Brother testimony, Mar-a-Lago recruitment, 5th Amendment on recruitment
        'flag_reason': 'Mark Epstein testified they "were friends" and Trump rode Epstein plane. Epstein pleaded 5th on Mar-a-Lago victim recruitment question. Multiple victims recruited from property.',
        'key_evidence': [
            {'type': 'document', 'summary': '"Terrific guy... likes beautiful women... on the younger side" quote 2002', 'confidence': 100},
            {'type': 'testimony', 'summary': 'Victim recruited from Mar-a-Lago', 'confidence': 80},
            {'type': 'photograph', 'summary': 'Multiple photos together at parties', 'confidence': 100},
            {'type': 'testimony', 'summary': 'Claims he banned Epstein from Mar-a-Lago', 'confidence': 60},
            {'type': 'deposition', 'summary': 'Mark Epstein: Trump and Jeffrey "were friends"', 'confidence': 90},
            {'type': 'deposition', 'summary': 'Mark Epstein: Trump rode on Epstein plane', 'confidence': 85},
            {'type': 'deposition', 'summary': 'Epstein pleaded 5th when asked if Maxwell recruited victim from Mar-a-Lago', 'confidence': 95},
            {'type': 'deposition', 'summary': 'Epstein confirmed visiting Mar-a-Lago, refused to say with whom', 'confidence': 90},
        ],
        'witnesses': ['Virginia Giuffre (saw at parties)', 'Mark Epstein (brother deposition)', 'Mar-a-Lago staff'],
        'confidence_score': 52,
    },
    'joi_ito': {
        'name': 'Joi Ito',
        'aliases': ['Joichi Ito'],
        'potential_charges': ['Concealing donations from convicted felon'],
        'status': 'Resigned from MIT Media Lab (2019)',
        'guilt_flag': 3,  # Took money knowing he was convicted, lied about it
        'flag_reason': 'Took donations from Epstein AFTER conviction. Tried to hide source. Resigned in disgrace. No abuse allegations.',
        'key_evidence': [
            {'type': 'email', 'summary': 'Emails show deliberate concealment of donations', 'confidence': 100},
            {'type': 'financial', 'summary': 'MIT received $850K+ from Epstein post-conviction', 'confidence': 100},
            {'type': 'document', 'summary': 'Internal emails called Epstein "voldemort" to hide name', 'confidence': 95},
            {'type': 'document', 'summary': 'Visited Epstein properties', 'confidence': 85},
        ],
        'witnesses': ['Whistleblower (Signe Swenson)'],
        'confidence_score': 48,
    },
}

# =============================================================================
# MCC DEATH ANOMALIES - FOIA FINDINGS
# =============================================================================

MCC_DEATH_ANOMALIES = {
    'suicide_watch_removal': {
        'finding': 'Epstein removed from suicide watch after ~24 hours',
        'anomaly': 'BOP average is 2.89 days, median 1.5 days. Removed extremely rapidly after clear attempt.',
        'sources': ['EFTA00036574', 'EFTA00034722', 'EFTA00036062'],
        'confidence': 95,
    },
    'incident_report_expunged': {
        'finding': 'Self-mutilation incident report expunged August 1, 2019',
        'anomaly': 'Officers documented noose around neck, but report expunged citing "insufficient evidence"',
        'sources': ['EFTA00034230'],
        'confidence': 100,
    },
    'cellmate_protocol_violation': {
        'finding': 'Cellmate removed August 9 and never replaced',
        'anomaly': 'PSYCH Alert status required cellmate. Died <24 hours after cellmate left.',
        'sources': ['EFTA00034778'],
        'confidence': 95,
    },
    'camera_failures': {
        'finding': 'Security cameras malfunctioned or had unusable footage',
        'anomaly': 'Critical cameras outside cell non-functional',
        'sources': ['MCC investigation docs'],
        'confidence': 90,
    },
    'guard_counts_missed': {
        'finding': 'Officers failed to conduct 3am and 5am counts',
        'anomaly': 'Officers later charged, were sleeping/browsing internet',
        'sources': ['EFTA00036062'],
        'confidence': 100,
    },
    'media_speculation': {
        'finding': 'BOP internally noted "media speculating he should not have been removed from SW"',
        'anomaly': 'Response focused on defending procedure rather than investigating',
        'sources': ['EFTA00036574'],
        'confidence': 100,
    },
}

# =============================================================================
# TIMELINE DATABASE
# =============================================================================

INVESTIGATION_TIMELINE = [
    # === 1990s - EARLY OPERATION ===
    {
        'date': '1991',
        'date_precision': 'year',
        'event': 'Epstein gets power of attorney over Les Wexner finances',
        'category': 'financial',
        'targets': ['les_wexner'],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '1992',
        'date_precision': 'year',
        'event': 'Ghislaine Maxwell begins relationship with Epstein after father death',
        'category': 'association',
        'targets': ['ghislaine_maxwell'],
        'confidence': 95,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '1994',
        'date_precision': 'year',
        'event': 'Jean-Luc Brunel founds MC2 Model Management',
        'category': 'trafficking',
        'targets': ['jean_luc_brunel'],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '1995',
        'date_precision': 'year',
        'event': 'Wexner transfers $77M NYC mansion to Epstein for $0',
        'category': 'financial',
        'targets': ['les_wexner'],
        'confidence': 100,
        'sources': [],
        'conflicts': ['Wexner claims it was a sale'],
    },
    {
        'date': '1996',
        'date_precision': 'year',
        'event': 'Virginia Giuffre recruited at Mar-a-Lago, age 16',
        'category': 'trafficking',
        'targets': ['ghislaine_maxwell', 'donald_trump'],
        'confidence': 90,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '1998',
        'date_precision': 'year',
        'event': 'Epstein purchases Little St. James island, USVI',
        'category': 'financial',
        'targets': [],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '1999',
        'date_precision': 'year',
        'event': 'Maria Farmer reports Epstein/Maxwell to FBI - no action taken',
        'category': 'legal',
        'targets': ['ghislaine_maxwell'],
        'confidence': 95,
        'sources': [],
        'conflicts': [],
    },
    # === 2000s - NETWORK EXPANSION ===
    {
        'date': '2001',
        'date_precision': 'year',
        'event': 'Giuffre trafficked to Prince Andrew in London, age 17',
        'category': 'trafficking',
        'targets': ['prince_andrew', 'ghislaine_maxwell'],
        'confidence': 85,
        'sources': [],
        'conflicts': ['Andrew denies ever meeting Giuffre'],
    },
    {
        'date': '2002-09',
        'date_precision': 'month',
        'event': 'Trump calls Epstein "terrific guy" who "likes them young"',
        'category': 'association',
        'targets': ['donald_trump'],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '2002',
        'date_precision': 'year',
        'event': 'Bill Clinton begins multiple flights on Lolita Express',
        'category': 'travel',
        'targets': ['bill_clinton'],
        'confidence': 90,
        'sources': [],
        'conflicts': ['Clinton denies island visits'],
    },
    {
        'date': '2005-03',
        'date_precision': 'month',
        'event': 'Palm Beach Police begin investigation after parent complaint',
        'category': 'legal',
        'targets': ['jeffrey_epstein'],
        'confidence': 100,
        'sources': [13026],
        'conflicts': [],
    },
    {
        'date': '2006-05',
        'date_precision': 'month',
        'event': 'FBI opens federal investigation',
        'category': 'legal',
        'targets': ['jeffrey_epstein'],
        'confidence': 100,
        'sources': [13026],
        'conflicts': [],
    },
    {
        'date': '2008-06-30',
        'date_precision': 'day',
        'event': 'Epstein pleads guilty to state prostitution charges',
        'category': 'legal',
        'targets': ['jeffrey_epstein', 'alexander_acosta'],
        'confidence': 100,
        'sources': [13016],
        'conflicts': [],
    },
    {
        'date': '2008-09',
        'date_precision': 'month',
        'event': 'Controversial federal non-prosecution agreement signed',
        'category': 'legal',
        'targets': ['jeffrey_epstein', 'alexander_acosta', 'alan_dershowitz'],
        'confidence': 100,
        'sources': [13016],
        'conflicts': [],
    },
    {
        'date': '2011',
        'date_precision': 'year',
        'event': 'Virginia Giuffre files civil lawsuit naming Prince Andrew',
        'category': 'legal',
        'targets': ['prince_andrew', 'ghislaine_maxwell'],
        'confidence': 100,
        'sources': [13015, 13020],
        'conflicts': [],
    },
    {
        'date': '2015-01',
        'date_precision': 'month',
        'event': 'Giuffre court filing names Dershowitz as abuser',
        'category': 'legal',
        'targets': ['alan_dershowitz', 'prince_andrew'],
        'confidence': 95,
        'sources': [13022],
        'conflicts': ['Dershowitz denies, counter-sues'],
    },
    {
        'date': '2019-07-06',
        'date_precision': 'day',
        'event': 'Epstein arrested at Teterboro Airport on federal charges',
        'category': 'legal',
        'targets': ['jeffrey_epstein'],
        'confidence': 100,
        'sources': [13031],
        'conflicts': [],
    },
    {
        'date': '2019-08-10',
        'date_precision': 'day',
        'event': 'Epstein found dead in MCC cell - ruled suicide',
        'category': 'death',
        'targets': ['jeffrey_epstein'],
        'confidence': 95,
        'sources': [13013],
        'conflicts': ['Conspiracy theories about murder persist'],
    },
    {
        'date': '2020-07-02',
        'date_precision': 'day',
        'event': 'Ghislaine Maxwell arrested in New Hampshire',
        'category': 'legal',
        'targets': ['ghislaine_maxwell'],
        'confidence': 100,
        'sources': [13011],
        'conflicts': [],
    },
    {
        'date': '2021-12-29',
        'date_precision': 'day',
        'event': 'Maxwell convicted on 5 of 6 counts',
        'category': 'legal',
        'targets': ['ghislaine_maxwell'],
        'confidence': 100,
        'sources': [13011],
        'conflicts': [],
    },
    {
        'date': '2022-02-19',
        'date_precision': 'day',
        'event': 'Jean-Luc Brunel found dead in Paris cell',
        'category': 'death',
        'targets': ['jean_luc_brunel'],
        'confidence': 100,
        'sources': [13012],
        'conflicts': ['Suicide vs murder debate'],
    },
    {
        'date': '2022-02',
        'date_precision': 'month',
        'event': 'Prince Andrew settles civil suit with Giuffre',
        'category': 'legal',
        'targets': ['prince_andrew'],
        'confidence': 100,
        'sources': [13020],
        'conflicts': [],
    },
    # === 2022-2024 - AFTERMATH ===
    {
        'date': '2022-03',
        'date_precision': 'month',
        'event': 'Leon Black steps down as Apollo chairman amid Epstein scrutiny',
        'category': 'legal',
        'targets': ['leon_black'],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '2022-06-28',
        'date_precision': 'day',
        'event': 'Ghislaine Maxwell sentenced to 20 years federal prison',
        'category': 'legal',
        'targets': ['ghislaine_maxwell'],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '2023-01',
        'date_precision': 'month',
        'event': 'JPMorgan settles with Epstein victims for $290 million',
        'category': 'financial',
        'targets': ['jes_staley'],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '2023-05',
        'date_precision': 'month',
        'event': 'Deutsche Bank settles with victims for $75 million',
        'category': 'financial',
        'targets': [],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '2023-07',
        'date_precision': 'month',
        'event': 'Virgin Islands settles with Epstein estate for $105 million',
        'category': 'legal',
        'targets': [],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
    {
        'date': '2024-01',
        'date_precision': 'month',
        'event': 'Court orders release of Epstein documents naming associates',
        'category': 'legal',
        'targets': ['prince_andrew', 'bill_clinton', 'donald_trump', 'alan_dershowitz'],
        'confidence': 100,
        'sources': [],
        'conflicts': [],
    },
]

# =============================================================================
# API FUNCTIONS
# =============================================================================

def get_flag_label(flag: int) -> str:
    """Get human-readable label for guilt flag"""
    if flag <= -2: return "CLEARED"
    if flag == -1: return "LIKELY VICTIM"
    if flag == 0: return "NO EVIDENCE"
    if flag <= 2: return "ASSOCIATION ONLY"
    if flag <= 4: return "SUSPICIOUS"
    if flag <= 6: return "CREDIBLE ACCUSATIONS"
    if flag <= 8: return "LIKELY GUILTY"
    if flag <= 10: return "SHOULD BE PROSECUTED"
    return "CONVICTED"


def get_prosecution_targets() -> List[Dict]:
    """Get all prosecution targets with their profiles"""
    targets = []
    for key, data in PROSECUTION_TARGETS_DB.items():
        flag = data.get('guilt_flag', 0)
        target = {
            'id': key,
            'name': data['name'],
            'aliases': data.get('aliases', []),
            'charges': data['potential_charges'],
            'status': data['status'],
            'confidence': data['confidence_score'],
            'guilt_flag': flag,
            'flag_label': get_flag_label(flag),
            'flag_reason': data.get('flag_reason', ''),
            'evidence_count': len(data.get('key_evidence', [])),
            'witnesses': data.get('witnesses', []),
        }
        targets.append(target)

    # Sort by guilt_flag descending (most guilty first)
    targets.sort(key=lambda x: x['guilt_flag'], reverse=True)
    return targets


def update_guilt_flag(target_id: str, new_flag: int, reason: str = None) -> Optional[Dict]:
    """Update guilt flag for a target (-2 to 12)"""
    if target_id not in PROSECUTION_TARGETS_DB:
        return None

    # Clamp to valid range
    new_flag = max(-2, min(12, new_flag))

    PROSECUTION_TARGETS_DB[target_id]['guilt_flag'] = new_flag
    if reason:
        PROSECUTION_TARGETS_DB[target_id]['flag_reason'] = reason

    # Recalculate confidence based on flag
    # Flag influences confidence: higher flag = higher confidence in guilt
    base_confidence = PROSECUTION_TARGETS_DB[target_id]['confidence_score']
    flag_boost = (new_flag / 12) * 20  # Up to 20% boost from flag
    new_confidence = min(100, base_confidence + flag_boost)
    PROSECUTION_TARGETS_DB[target_id]['confidence_score'] = int(new_confidence)

    return {
        'target_id': target_id,
        'guilt_flag': new_flag,
        'flag_label': get_flag_label(new_flag),
        'flag_reason': PROSECUTION_TARGETS_DB[target_id].get('flag_reason', ''),
        'confidence_score': PROSECUTION_TARGETS_DB[target_id]['confidence_score']
    }


def get_target_profile(target_id: str) -> Optional[Dict]:
    """Get detailed profile for a specific target"""
    if target_id not in PROSECUTION_TARGETS_DB:
        return None

    data = PROSECUTION_TARGETS_DB[target_id]

    # Get related timeline events
    timeline = [e for e in INVESTIGATION_TIMELINE if target_id in e.get('targets', [])]

    flag = data.get('guilt_flag', 0)
    return {
        'id': target_id,
        'name': data['name'],
        'aliases': data.get('aliases', []),
        'potential_charges': data['potential_charges'],
        'status': data['status'],
        'confidence_score': data['confidence_score'],
        'guilt_flag': flag,
        'flag_label': get_flag_label(flag),
        'flag_reason': data.get('flag_reason', ''),
        'evidence': data.get('key_evidence', []),
        'witnesses': data.get('witnesses', []),
        'timeline': timeline,
    }


def get_timeline(category: str = None, target: str = None) -> List[Dict]:
    """Get investigation timeline, optionally filtered"""
    events = INVESTIGATION_TIMELINE.copy()

    if category:
        events = [e for e in events if e.get('category') == category]

    if target:
        events = [e for e in events if target in e.get('targets', [])]

    # Sort by date
    events.sort(key=lambda x: x['date'])
    return events


def calculate_prosecution_readiness(target_id: str) -> Dict:
    """Calculate how ready a case is for prosecution"""
    if target_id not in PROSECUTION_TARGETS_DB:
        return {'ready': False, 'score': 0, 'missing': ['Target not found']}

    data = PROSECUTION_TARGETS_DB[target_id]

    score = 0
    missing = []
    strengths = []

    # Evidence quality (40 points max)
    evidence = data.get('key_evidence', [])
    if len(evidence) >= 3:
        score += 20
        strengths.append(f"{len(evidence)} pieces of evidence")
    else:
        missing.append(f"Need more evidence (have {len(evidence)})")

    # High confidence evidence
    high_conf = [e for e in evidence if e.get('confidence', 0) >= 80]
    if len(high_conf) >= 2:
        score += 20
        strengths.append(f"{len(high_conf)} high-confidence items")
    else:
        missing.append("Need more corroborated evidence")

    # Witnesses (30 points max)
    witnesses = data.get('witnesses', [])
    if len(witnesses) >= 2:
        score += 30
        strengths.append(f"{len(witnesses)} potential witnesses")
    elif len(witnesses) == 1:
        score += 15
        missing.append("Need additional witnesses")
    else:
        missing.append("No witnesses identified")

    # Timeline events (15 points max)
    timeline = [e for e in INVESTIGATION_TIMELINE if target_id in e.get('targets', [])]
    if len(timeline) >= 2:
        score += 15
        strengths.append(f"{len(timeline)} dated events")
    else:
        missing.append("Need more timeline documentation")

    # Legal status (15 points max)
    status = data.get('status', '')
    if 'convicted' in status.lower():
        score += 15
        strengths.append("Already convicted")
    elif 'charged' in status.lower():
        score += 10
        strengths.append("Charges filed")
    elif 'settled' in status.lower():
        score += 5
        strengths.append("Civil settlement (may indicate guilt)")
    else:
        missing.append("No legal action taken yet")

    return {
        'target': data['name'],
        'ready': score >= 70,
        'score': score,
        'strengths': strengths,
        'missing': missing,
        'recommendation': 'Strong case' if score >= 70 else 'Needs more evidence' if score >= 40 else 'Insufficient for prosecution'
    }


def get_evidence_chain(target_id: str) -> List[Dict]:
    """Get the chain of evidence for a target"""
    if target_id not in PROSECUTION_TARGETS_DB:
        return []

    data = PROSECUTION_TARGETS_DB[target_id]
    evidence = data.get('key_evidence', [])

    chain = []
    for i, e in enumerate(evidence):
        chain.append({
            'order': i + 1,
            'type': e.get('type'),
            'summary': e.get('summary'),
            'confidence': e.get('confidence', 0),
            'strength': 'Strong' if e.get('confidence', 0) >= 80 else 'Moderate' if e.get('confidence', 0) >= 50 else 'Weak'
        })

    return chain


# =============================================================================
# SUMMARY FUNCTIONS
# =============================================================================

def get_prosecution_summary() -> Dict:
    """Get overall prosecution readiness summary"""
    targets = get_prosecution_targets()

    ready = [t for t in targets if t['confidence'] >= 70]
    needs_work = [t for t in targets if 40 <= t['confidence'] < 70]
    insufficient = [t for t in targets if t['confidence'] < 40]

    return {
        'total_targets': len(targets),
        'prosecution_ready': len(ready),
        'needs_more_evidence': len(needs_work),
        'insufficient': len(insufficient),
        'top_targets': [{'name': t['name'], 'confidence': t['confidence']} for t in targets[:5]],
        'timeline_events': len(INVESTIGATION_TIMELINE),
        'convictions': 1,  # Maxwell
        'deaths_in_custody': 2,  # Epstein, Brunel
    }
