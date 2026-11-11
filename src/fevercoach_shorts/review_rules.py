HISTORICAL_FAIL_PREVENTION_RULES = """
Historical FeverCoach reviewer failure-prevention rules (derived from 171 failed reviews):
1. Numeric medication safety: never state or visualize an mL dose unless the source provides the
   child's weight, active ingredient, product concentration, route, and applicable instruction.
   Never use a temperature alone as permission to alternate medicines. Do not generalize a
   case-specific dose, interval, test, or prescription.
2. Speak ranges unambiguously. In Korean say "5에서 7.5밀리리터" and "4시간에서 6시간",
   not bare adjacent numbers that can sound like 57.5 or 46. Pronounce mL as "밀리리터".
   Apply equivalent natural range grammar in English and Spanish. Audio, captions, and overlays
   must carry the same number, unit, meaning, and language.
3. Medical wording: distinguish newborn (under 28 days) from infant. Do not turn correlations,
   common patterns, color of mucus, timing such as 48 hours, or a single temperature into a
   diagnosis, absolute rule, or treatment threshold. Preserve uncertainty and case context.
4. Urgency: do not delay care for respiratory distress, apnea, cyanosis, altered responsiveness,
   severe dehydration, seizure, concerning rash, or persistent/severe fever. Separate emergency
   care, same-day evaluation, routine follow-up, and home observation when supported by the source.
5. Medication/device route (strict FeverCoach publishing rule): any syringe in or near a mouth is
   an automatic FAIL, including a needleless oral dosing syringe. Show swallowed medicine only as
   an age-appropriate tablet/capsule when the source supports that form, or as liquid medicine sipped
   from a purpose-made dosing cup. Never use a kitchen spoon. Show a needle and syringe only when the
   source explicitly requires an injection; direct it to an appropriate skin, muscle, or IV site and
   keep it completely away from the mouth. Never infer injection from generic words such as give,
   administer, dose, medicine, or medication.
6. Demonstration safety: never measure axillary temperature over clothing; keep hair and sweat away
   from a forehead measurement and do not overstate forehead thermometer precision. Never feed an
   infant lying flat, cut a pacifier, recommend inhalable powder, force-feed, or improvise unsafe
   sleep positioning. Show age-appropriate tools and posture.
7. Generated visuals: all model-generated labels, packages, calendars, thermometers, charts, signs,
   and screens must stay blank. Readable words, numbers, and units are rendered only by code. Reject
   malformed anatomy, extra fingers/limbs, impossible devices, and visuals that contradict narration.
8. Language and captions: the file's declared language, narration, captions, and overlays must match.
   Reject garbled glyphs, encoding replacement characters, mistranslations, omitted words, clipped
   sentences, missing captions, and TTS/caption disagreements.
9. Media integrity: reject black/frozen/missing sections, silent or cut-off narration, bad sync,
   missing audio/video streams. Use hashes to establish duplicate identity; identical bytes under a
   revised filename do not prove a repair. Duplication alone is not a medical FAIL.
10. Every claim and action shown must directly support the current scene's source-grounded narration.
    Do not fill time with unrelated medical imagery or invent history, tests, diagnoses, or outcomes.
""".strip()


SUBMISSION_FEEDBACK_CALIBRATION_RULES = """
Recent FeverCoach submission-feedback calibration rules (derived from the September 2026
multilingual reviewer set):
1. Complete speech: listen through the final syllable of every scene. A trailing fragment,
   unfinished clause, abruptly cut word, or sentence that ends only because the scene changes is
   not acceptable. Examples such as a voice ending at "38도 열에..." are INCOMPLETE_SPEECH,
   normally medium/FAIL when the intended meaning is lost.
2. Caption coverage: compare the actually spoken audio with the actually visible burned-in captions
   clause by clause, not merely with the planned caption JSON. Captions may be split or condensed
   only if every medical condition, negation, number, unit, interval, red flag, and action remains.
   Omission of a safety-relevant clause is CAPTION_OMISSION and normally medium/FAIL; omission of
   optional explanatory detail is low/WARN.
3. Medication timing: a recommendation to alternate fever medicines every two hours is unsafe or
   materially incomplete unless it clearly identifies different active ingredients, keeps each
   product on its own permitted interval and daily maximum, prevents duplicate ingredients, and is
   grounded in a clinician/source instruction. Flag an unsupported or underspecified two-hour
   alternating schedule as MEDICATION_TIMING_RISK; do not "repair" it by inventing a dose.
4. Triage completeness: when the case includes persistent fever with new ear/chest
   pain, respiratory noise or distress, inability to drink, dehydration, cyanosis, apnea, seizure,
   or reduced responsiveness, verify that the spoken and captioned action level is adequate. Do not
   replace same-day/in-person or emergency evaluation with vague monitoring language. Missing an
   action that could delay urgent care is TRIAGE_OMISSION and medium/high FAIL.
5. Respiratory red flags: for infant stridor/wheeze or suspected airway narrowing, specifically look
   for rapid worsening, retractions/chest indrawing, cyanosis, apnea, poor feeding, or lethargy when
   supported by the source. A short video need not list every sign, but it must not omit the source's
   decisive reason for prompt evaluation.
6. High fever context: when 40°C or another very high temperature is central, check age-specific
   risk and care thresholds—especially young infants—and the child's overall condition. Temperature
   alone must not be portrayed as either automatically benign or a diagnosis. Flag missing urgent
   age/context guidance only when the source or accepted safety standard makes it material.
7. Clinical distinctions: when discussing sleep after fever, explicitly distinguish normal recovery
   sleep (rouses and responds) from pathological lethargy/altered responsiveness (difficult to wake,
   weak or absent response). When discussing oral ulcers or inability to drink, connect this to
   dehydration observation and appropriate evaluation. Do not let reassuring language erase these
   distinctions.
8. Treatment completeness without invention: for influenza or similar topics, missing supported
   home care (comfort-directed antipyretic use, fluids) or source-supported antiviral guidance may
   be low/WARN. Escalate only if the omission makes the advice unsafe. Never add a treatment that is
   absent from the source merely to satisfy this checklist.
9. Multilingual parity: apply the same checks independently to Korean, English, and Spanish. Numeric
   intervals such as 12 hours and safety qualifiers must appear in both speech and captions in that
   language. A good translation in another language does not excuse a clipped or incomplete version.
10. Feedback severity calibration: reviewer "good" is positive evidence, "ok" usually means a
    non-blocking improvement unless safety meaning is missing, and "uncertain" requires focused
    verification rather than automatic failure. Use observable evidence, source comparison, and
    confidence; do not manufacture omissions just to fill the checklist.
""".strip()


REVIEW_GUIDELINE_VERSION = "2026-10-05.jaeyoon-fail-only.v4"

# The attachment contains 50 reviewer rows for 25 filenames, including Spanish-v1.
# These are calibration examples, not fresh verdicts on subsequently repaired videos.
SEPTEMBER_13_REVIEW_RULES = """
September 13 reviewer adjudication (set1-set8, MC and Sam; supersedes conflicting older examples):
1. Evidence and polarity: read the complete clause and adjacent scenes before judging. Distinguish
   recommendation, warning against an action, patient history/question, and hypothetical example.
   "Alternating every two hours may be excessive" is a warning, not a dosing recommendation.
   Do not infer safety from "good" comments or a P alone: the same row may contain corrections.
   Explicit F reasons need investigation, not blind reuse against a different/repaired file.
2. Whole-video urgency: compare every home-care, wait, and seek-care statement across scenes in
   audio, captions, and overlays. An early or final emergency warning does not cancel conflicting
   advice to wait until tonight/오늘 저녁/esta noche, six hours, or tomorrow for the SAME red flag.
   Quote both timestamps and their patient conditions in the issue evidence. A real delay for
   worsening infant breathing or reduced responsiveness is high MEDICAL_ERROR/TRIAGE_OMISSION.
3. Set1: a day-four fever case with NEW chest pain needs prompt in-person reassessment. It is not
   permission for every child to wait four days. Do not animate pain physically travelling from
   ear to chest along nerves/vessels or say shift/move as a causal mechanism. Do not imply that
   auscultation alone confirms or excludes pneumonia. Preserve case context and diagnostic limits.
4. Set2/set7 medication: prefer one appropriate antipyretic for distress. A routine 2-3-hour
   alternating schedule without a clinician plan and each ingredient's minimum interval/daily
   maximum is MEDICATION_TIMING_RISK. A warning AGAINST that schedule is not an error. At 12 kg,
   160 mg acetaminophen is about 13.3 mg/kg, but 5 mL equals 160 mg ONLY at 160 mg/5 mL concentration.
   Identify weight, drug, concentration, route and dose context together for an actionable volume.
   Do not apply "4-6 hours" to unnamed fever medicines or conflate acetaminophen with ibuprofen.
   Verify product/age-specific minimum intervals and daily limits; do not invent a universal limit.
5. Set3 respiratory: distinguish lower-airway wheeze from upper-airway stridor; a reported metallic
   sound alone is not a confirmed diagnosis. Worsening infant breathing needs assessment now.
   Severe distress, chest indrawing or blue lips require immediate emergency help. The symptom
   condition AND action must be audible and captioned; isolated "call 119 immediately" is incomplete.
   Emergency numbers follow the known distribution country, not the language. If the country is
   unknown, use "local emergency services"; do not assume all English/Spanish audiences use 911/119.
6. Set4 age exceptions: when reassuring viewers about a baby's 40°C fever, state age restrictions
   before or with the first home-care advice, not only at the end. Under 3 months with >=38°C needs
   immediate medical assessment; 3-6 months with >=39°C needs prompt assessment. Repeated >40°C
   merits prompt clinician contact even in an older child. Do not make every 40°C case an ambulance
   indication or suggest waiting three days solely because the infant looks active.
7. Set6 sleep: "3-4 hours deep sleep is normal", "check after six hours", or "seek care tomorrow
   if lethargy persists" are not validated safety cutoffs. Judge ability to rouse and respond as
   usual. Unusual difficulty waking or reduced response needs immediate assessment regardless of
   elapsed sleep time; absent response needs emergency help. A clock must not imply waiting is safe.
8. Swallowing and sleep visuals: oral fluid/medicine only while sufficiently awake and able to
   swallow safely, supported upright; never pour into a sleeping/unresponsive child's mouth.
   Infant sleep demonstrations use a firm flat surface, supine placement and fitted sheet only;
   remove pillows, loose blankets and soft toys. Flag actual unsafe depiction as OTHER_VISUAL_ERROR,
   not a harmless decoration. Do not substitute an age-inappropriate tablet to avoid an oral syringe.
9. Set5/set7 claims: do not state steroids increase viral shedding in HFMD without applicable
   evidence. Prefer qualified wording that steroids are not routinely recommended for uncomplicated
   HFMD; do not instruct stopping a prescribed drug. Day-five improvement is not guaranteed recovery;
   usual HFMD recovery is about 7-10 days with variation. Do not promise fever resolution within
   24-48 hours of antivirals. Distinguish sports drinks from ORS; infant hydration is primarily
   breast milk/formula, with appropriate ORS guidance when indicated and safe swallowing possible.
10. Set8 drug-specific redosing: reject blanket "vomit within one hour, immediately repeat a full
    dose". For pediatric oseltamivir, Medicines for Children distinguishes vomiting before 30
    minutes (same dose again) from after 30 minutes (no repeat; next usual dose). Do not extrapolate
    this rule to all drugs, invent an exact-30-minute boundary, or ignore repeated vomiting;
    uncertain/repeated cases need prescriber/pharmacist advice and applicable prescription guidance.
    Twice-daily roughly 12-hour dosing refers to oseltamivir TREATMENT, not all influenza medicines
    or prevention regimens. First-day schedule changes need clinician/pharmacist confirmation.
11. Avoid false failures: case-day counts are not waiting instructions unless presented as such.
    Optional room-temperature preferences and duplicate filenames alone are not medical failures.
    Source-detail omission is not CAPTION_OMISSION unless the detail was spoken but absent on screen.
    A fact safely explained elsewhere need not repeat in every scene, except when a local condition
    is necessary to prevent unsafe advice. Broader safe triage is not a numeric error: never require
    39°C before seeking help for seizures merely because a source example had 39°C.
12. Repairs must preserve meaning: do not compress separate red flags into "48-hour fever/lethargy"
    (implies waiting for lethargy) or "palm swelling" (loses injection SITE and SIZE). Use complete,
    plain-language conditional clauses. If essential advice cannot fit, flag the need to replan
    duration/scenes; do not drop a safety condition or force unintelligibly fast TTS to obtain PASS.
    Source fidelity never requires repeating unsafe source advice; cite the safety conflict and
    verified reference, and request human review when the correction is not established.
13. Verdict: a demonstrated material dosing/triage/unsafe-action defect is FAIL even if other scenes
    are good. Optional clarification is low/WARN; unclear evidence needs a limitation, not a made-up
    failure or a fabricated PASS. Use existing MEDICAL_ERROR, UNSUPPORTED_CLAIM, NUMERIC_ERROR,
    CLINICAL_DISTINCTION_MISSING, MEDICATION_TIMING_RISK, TRIAGE_OMISSION, OTHER_VISUAL_ERROR,
    INCOMPLETE_SPEECH and CAPTION_OMISSION categories as appropriate.

Verified references (2026-09-13; these are specific safety references, not the video's source article):
- NICE NG143, age risks and antipyretic distress/alternation:
  https://www.nice.org.uk/guidance/ng143/chapter/recommendations
- NHS fever triage and responsiveness: https://www.nhs.uk/symptoms/fever-in-children/
- Medicines for Children, oseltamivir:
  https://www.medicinesforchildren.org.uk/medicines/oseltamivir-for-influenza-flu/
- CDC HFMD recovery: https://www.cdc.gov/hand-foot-mouth/index.html
- CDC infant sleep: https://www.cdc.gov/sudden-infant-death/sleep-safely/
- AAP repeated high fever:
  https://www.healthychildren.org/English/health-issues/conditions/fever/Pages/When-to-Call-the-Pediatrician.aspx
""".strip()

SUBMISSION_FEEDBACK_CALIBRATION_RULES += "\n\n" + SEPTEMBER_13_REVIEW_RULES

WEEK8_REVIEW_RULES = """
September 21 week8 feedback (60 distinct files, MC/Sam 120 rows, 30 F and 30 P):
1. Treat each language's actual video/topic as the unit of review. Numbered uploads shift across
   KO/EN/ES (for example, week8-English-25 is cough while KO/ES-25 are feeding). Never propagate
   a verdict or repair by set number alone; match the source URL, topic, language and exact media.
   A P may still request clearer visuals or wording. A clipped spoken sentence is evaluated even
   when its medical topic received P.
2. Antipyretics: answer a question about simultaneous dosing explicitly: do not recommend giving
   acetaminophen and ibuprofen together. Prefer one age-appropriate medicine for discomfort.
   Only consider alternating for persistent/recurrent distress with each medicine's own minimum
   interval and daily maximum recorded; do not infer a routine 2-3-hour schedule from fever alone.
   A 2-3-hour separation is not intrinsically always forbidden. Ibuprofen under 6 months needs
   clinician direction; ensure that qualifier is preserved in EN as well as KO/ES. "Six hours have
   passed" alone is not an instruction to dose a comfortable sleeping child. Verify concentration:
   40 kg + 15 mL of 32 mg/mL acetaminophen = 480 mg (12 mg/kg); 41 kg + 17-24 mL of 12 mg/mL
   ibuprofen = 204-288 mg (about 5-7 mg/kg). These are case/product examples, not universal mL doses.
   A more conservative interval is not automatically overdose. Show an age/weight-appropriate child
   and a purpose-made graduated dosing cup matching the spoken device and volume; do not visually
   imply the same mL applies to a smaller infant.
3. Medication handling: a fixed 1-2-hour use window and refrigeration for premixed antipyretic
   powder cannot be generalized without the drug, formulation and label. Give product/pharmacist
   instructions instead. Do not tell parents to stop and restart an unidentified prescribed
   intestinal medicine whenever stools change. Specify the medication and prescribing plan or ask
   the clinician/pharmacist. Three loose stools alone do not always mean an emergency; distinguish
   blood, severe pain, dehydration and reduced alertness. Keep the earlier oseltamivir-specific
   vomit/redose rule; do not replace it with a generic one-hour rule.
4. Infant feeding: "seek care only after 12 hours refusing feeds" is too broad for a young baby
   who is taking very little or becoming lethargic. Compare with usual intake, wet diapers,
   activity and age; advise earlier evaluation for almost no intake or concerning appearance.
   Do not prescribe 30-50 mL every 30 minutes across all infant ages. If formula amount is reduced
   for a vomiting baby, explicitly mean a smaller amount PER FEED while mixing at the NORMAL LABEL
   CONCENTRATION; never suggest reducing powder concentration. Show a prepared normal-concentration
   feed and smaller serving, not mysterious liquid drops diluting a bottle. A pause in solids is
   not a pause in breast milk/formula or age-appropriate hydration. Support head and trunk upright
   while feeding. Keep age-specific fever exceptions, especially under 3 months with >=38°C.
5. Infant sleep and thermoregulation: do not teach "one layer less than an adult" as a universal
   fever rule. Avoid over-wrapping or underdressing according to environment and child's condition.
   Warm hands/feet alone do not prove normal circulation or general safety. For infants, no pillows,
   soft bumpers or loose blankets; a raised pillow can be depicted only for an older child when
   appropriate. Do not claim an actual suffocation event without evidence.
6. Nasal irrigation: never demonstrate a bottle aimed into the nose of a child lying flat with head
   tilted back. If an older cooperative child uses an age-appropriate rinse, show them leaning
   forward over a sink and following product/clinician instructions. Distinguish infant saline
   drops/gentle suction from bottle irrigation. Rinse solution requires sterile/distilled or
   previously boiled and cooled water; device hygiene matters. CT is clinician-selected, not a
   routine test for every prolonged stuffy nose. Do not infer actual aspiration from a bad pose.
7. Infection and follow-up: RSV can worsen without fever and "2-3 days passed" is not a safety
   guarantee. New fever or yellow mucus alone does not prove bacterial infection. After treated
   pneumonia, 10 days and 3 weeks may be CASE HISTORY, never universal wait-until deadlines for
   re-evaluation or automatic X-ray/blood tests. New/persistent fever or worsening breathing,
   intake or activity needs earlier assessment. Conversely, routine follow-up X-ray is often not
   needed after uncomplicated clinical recovery, with clinician-selected exceptions; do not cancel
   a prescribed test. Mycoplasma symptoms can appear 1-4 weeks after exposure; exposure alone
   does not justify preventive antibiotics, and not every mild infection needs antibiotics. A dry
   cough alone is not diagnostic. Do not label every 38°C reading "high fever".
8. Imaging and home care: a persistent scalp bump is not automatically a hematoma, nor does every
   bruise vanish in one week. Distinguish scalp/subperiosteal from intracranial bleeding in visuals.
   A humidifier needs cleaning. Antibiotics do not directly suppress cough but may improve cough
   when treating a relevant bacterial cause. Avoid guaranteed fever resolution 24-48 hours after
   antiviral treatment and sports drinks presented as equivalent to ORS.
9. Adjudication: quote the scene's literal narration and show how the visual changes its meaning.
   Ambiguous "reduce formula to two-thirds" plus apparent bottle dilution merits a safety fix;
   do not claim it explicitly instructed dilution unless it did. A 4-6-hour wait for SOLIDS is not
   necessarily fluid fasting. A conservative dose interval is not automatically overdose. Do not
   invent harm (aspiration, hypothermia, suffocation) that was not shown. Correct the unsafe
   ambiguity while preserving all already-correct red flags and cross-language qualifications.

Clinical references checked 2026-09-21:
- NICE fever/antipyretics: https://www.nice.org.uk/guidance/ng143/chapter/recommendations
- AAP ibuprofen under 6 months:
  https://www.healthychildren.org/English/safety-prevention/at-home/medication-safety/Pages/Ibuprofen-for-Fever-and-Pain.aspx
- CDC infant formula instructions:
  https://www.cdc.gov/infant-toddler-nutrition/formula-feeding/preparation-and-storage.html
- FDA nasal rinsing water and age-appropriate use:
  https://www.fda.gov/consumers/consumer-updates/rinsing-your-sinuses-neti-pots-safe
- CDC RSV infants: https://www.cdc.gov/rsv/infants-young-children/index.html
- CDC Mycoplasma: https://www.cdc.gov/mycoplasma/about/index.html
- Medicines for Children powder preparations:
  https://www.medicinesforchildren.org.uk/advice-guides/giving-medicines/how-to-give-medicines-granules-and-powders/
""".strip()

SUBMISSION_FEEDBACK_CALIBRATION_RULES += "\n\n" + WEEK8_REVIEW_RULES

JAEYOON_FAIL_ONLY_RULES = """
October 5 Jaeyoon FAIL-only update (76 F review rows, 69 distinct filenames):
Scope: only Jaeyoon-named files with an explicit F/FAIL in the supplied review table contributed
to this update. Other creators, P rows and unrated rows did not. Earlier safety rules remain.
Feedback identifies risks to investigate, not a new verdict on an unseen or repaired video.
1. Formulation and storage must agree in speech, captions, props and overlays. An oral pediatric
   antibiotic syrup must not become an injection vial labelled Pro-Pen-G Injection, an adult tablet,
   or a capsule. Generated containers stay text-free; code-rendered labels must match the verified
   ingredient, formulation and route. Do not invent packaging text or storage instructions.
   Do not explain refrigeration only as preserving taste/smell or declare all antibiotics safe
   after six hours outside refrigeration. Stability/potency and permitted storage depend on the
   exact product, preparation and exposure; use its label or pharmacist advice. Neither normal
   appearance nor a color/lump change alone establishes a universal keep/discard rule. Do not
   literally visualize or translate a hot parked car as a burning car.
2. Do not state that fever naturally cycles every 4-6 hours. A drug's dosing interval or temporary
   symptom relief is not a universal fever rhythm. Preserve uncertainty and the actual case.
   Distinguish a fever definition from a care threshold: 38/38.5°C alone does not make every older,
   otherwise well child an emergency. Conversely, never remove young-infant age exceptions or
   urgent care for breathing difficulty, dehydration or reduced responsiveness. Use known age,
   associated symptoms and illness course; do not replace blanket emergency advice with blanket
   permission to wait three days. Reviewer criticism of a cutoff does not override infant safety.
3. Retractions mean localized soft-tissue indrawing with inspiration, not ribs breaking, folding,
   or a torso morphing between external anatomy and an unexplained cutaway. Never label ordinary
   breathing as demonstrated retractions. If the sign cannot be depicted accurately within the
   visual contract, show a caregiver seeking care and retain the symptom/action in narration and
   captions. Do not claim a neutral caregiver shot demonstrates the physical sign.
4. Saline: distinguish discrete infant drops/gentle suction from sustained bottle irrigation.
   Match a stated, source-supported drop count to the action; do not invent a universal count.
   Inspect the actual sequence and scale before alleging excessive volume. Conflicting reviews
   of week8-1 do not establish overdose or aspiration. Check infant bedding independently.
5. Reinforce prior F-derived safety checks: one antipyretic for discomfort before any clinician-
   guided alternation; explicitly answer simultaneous-versus-alternating questions; retain each
   ingredient's intervals, concentration and age qualifiers. No generic one-hour full redosing,
   premix/refrigeration deadline, unidentified medicine stop/restart, 12-hour feed-refusal wait,
   dilution of formula, clock-based reassurance for lethargy, or fixed post-pneumonia waiting
   deadline. No guarantee of antiviral response. Conditions and actions must both survive KO/EN/ES
   TTS and captions, including negations, numeric ranges and units. Review the actual full audio.
6. Adjudicate with observed evidence: quote the literal speech/caption, relevant visual and time;
   for contradictory urgency quote BOTH statements and establish that they concern the same
   condition. Separate unsafe depiction from an unobserved injury (aspiration/suffocation etc.).
   An ambiguous or unreadable sign needs an explicit limitation, not invented evidence or PASS.
   Missing optional source detail is not an audio-caption omission. Do not promote every Note
   into a medical FAIL or copy a verdict from a differently numbered language file.
7. Duplicate submissions: assert identical bytes only from supplied/computed hashes, never from
   similar names or an old reviewer note. Unchanged bytes are not proof of repair; retain the
   applicable earlier result and distinguish submission duplication from medical defects. A new
   hash alone is not proof of safety either. Recheck actual language instead of inferring it.
8. These checks are screening, not physician approval. Do not force PASS, fabricate clinical
   references, or claim a fresh video audit from prompt updates alone. If required age/product or
   video evidence is unavailable, state that limitation and request review instead of guessing.
""".strip()

JAEYOON_VISUAL_SAFETY_RULES = """
Jaeyoon FAIL-derived visual guardrails:
- Keep the same source-supported oral/injection route and pediatric formulation throughout;
  no injection-labelled props or adult capsules for a syrup topic. All generated labels stay blank.
- Never put any syringe in or near a mouth (FeverCoach publishing constraint). Do not substitute
  an age-inappropriate pill. If safe oral administration cannot be shown, show caregiver guidance.
- Do not morph, fold or break ribs to illustrate retractions, or label normal breathing as a
  red flag. Use an anatomically accurate medical schematic only when the visual contract allows
  it; otherwise show seeking care, without pretending to demonstrate the physical sign.
- Source-supported infant saline drops are discrete drops, not a sustained squeeze-bottle stream.
  Do not introduce a numeric dose. Keep age-appropriate nasal care distinct from adult irrigation.
- Depict a hot parked car without flames; heat exposure does not mean a burning vehicle.
- A source frame already containing an unsafe device, posture or anatomical distortion requires
  reference repair, not a claim that subsequent camera motion will make that frame safe.
""".strip()

SUBMISSION_FEEDBACK_CALIBRATION_RULES += "\n\n" + JAEYOON_FAIL_ONLY_RULES

ADJUDICATION_CHECK_NAMES = (
    "recommendation_vs_warning", "cross_scene_urgency", "dose_concentration_context",
    "drug_specific_redosing", "respiratory_sound_distinction", "emergency_locale",
    "safe_sleep_and_swallowing", "mechanism_and_diagnostic_limits",
    "treatment_claim_uncertainty",
    "simultaneous_and_alternating_antipyretics", "infant_feeding_and_formula",
    "medicine_storage_and_restart", "age_appropriate_nasal_care",
    "case_timeline_vs_wait_instruction", "cross_language_topic_identity",
    "formulation_storage_consistency", "fever_cycle_and_triage_context",
    "retraction_anatomy", "saline_action_evidence",
)


def extend_review_schema(schema: dict) -> None:
    """Keep both Gemini QA entry points on the same required adjudication checks."""
    checks = schema["properties"]["calibration_checks"]
    for name in ADJUDICATION_CHECK_NAMES:
        if name not in checks["required"]:
            checks["required"].append(name)
        checks["properties"][name] = {
            "type": "string", "enum": ["PASS", "FAIL", "NOT_APPLICABLE"]
        }
