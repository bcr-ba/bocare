import requests
import json
import logging
import uuid
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from langdetect import detect, LangDetectException
from config import OPENROUTER_API_KEY
from medical_knowledge import MedicalKnowledgeBase, PatientSession
from safety_utils import input_validator, safety_monitor
from web_rag_system import web_rag_system
from response_quality import response_quality_enhancer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('medical_chatbot.log'),
        logging.StreamHandler()
    ]
)

class EnhancedMedicalChatbot:
    """Enhanced Medical Chatbot with RAG, conversation management and intelligent triage"""
    
    def __init__(self):
        self.knowledge_base = MedicalKnowledgeBase()
        self.active_sessions: Dict[str, PatientSession] = {}
        self.conversation_state = {
            'current_session': None,
            'awaiting_response': False,
            'current_questions': []
        }
        self.default_language = 'fr'
        logging.info("Enhanced Medical Chatbot initialized with advanced security and RAG")
    
    def set_default_language(self, language: str):
        """Set default language for responses"""
        self.default_language = language
    
    def start_new_consultation(self, language: str = None) -> Tuple[str, str]:
        """Initialize a new patient consultation session"""
        session_id = str(uuid.uuid4())
        
        # Use provided language or default
        session_language = language or self.default_language
        
        # Create new session
        session = PatientSession(
            session_id=session_id,
            initial_symptoms=[],
            conversation_history=[],
            follow_up_questions=[],
            responses={},
            urgency_level=1,
            recommended_action="",
            timestamp=datetime.now(),
            language=session_language
        )
        
        self.active_sessions[session_id] = session
        self.conversation_state['current_session'] = session_id
        
        # Language-dependent welcome message
        if session.language == 'fr':
            welcome_message = (
                "🏥 **Bonjour et bienvenue dans BoCare AI Assistant**\n\n"
                "Je suis votre assistant médical intelligent. Mon rôle est de vous accompagner "
                "pour mieux comprendre vos symptômes et vous orienter vers les soins appropriés.\n\n"
                "**Comment puis-je vous aider aujourd'hui ?**\n"
                "Décrivez-moi ce qui vous préoccupe, vos symptômes ou votre état de santé actuel."
            )
        else:
            welcome_message = (
                "🏥 **Hello and welcome to BoCare AI Assistant**\n\n"
                "I am your intelligent medical assistant. My role is to help you better understand "
                "your symptoms and guide you to appropriate care.\n\n"
                "**How can I help you today?**\n"
                "Please describe what concerns you, your symptoms, or your current health condition."
            )
        
        logging.info(f"New consultation started - Session ID: {session_id} - Language: {session.language}")
        return welcome_message, session_id
    
    def process_user_input(self, user_input: str, session_id: Optional[str] = None) -> str:
        """Process user input with intelligent conversation management and multilingual consistency"""
        try:
            validation_result = input_validator.validate_input(user_input, session_id)
            if not validation_result.is_valid:
                logging.warning(f"Invalid input rejected: {user_input[:60]}...")
                return validation_result.error_message or ("Invalid input" if self.default_language == 'en' else "Entrée invalide")

            user_input = validation_result.sanitized_input

            if not session_id or session_id not in self.active_sessions:
                _, session_id = self.start_new_consultation(self.default_language)
            session = self.active_sessions[session_id]

            if validation_result.warning_message:
                if 'URGENT' in validation_result.warning_message or 'URGENT' in user_input.upper():
                    safety_monitor.log_emergency_detection(session_id, user_input)
                logging.warning(f"Session {session_id}: {validation_result.warning_message}")

            # Language detection (robust)
            try:
                detected_lang = detect(user_input)
                if detected_lang.startswith('fr'):
                    session.language = 'fr'
                elif detected_lang.startswith('en'):
                    session.language = 'en'
            except LangDetectException:
                pass  # keep session language

            session.conversation_history.append({
                'role': 'user', 'content': user_input, 'timestamp': datetime.now().isoformat()
            })

            detected_symptoms, urgency_level, specialist = self.knowledge_base.analyze_symptoms(user_input)
            session.initial_symptoms.extend(detected_symptoms)
            session.urgency_level = max(session.urgency_level, urgency_level)
            if urgency_level >= 4:
                safety_monitor.log_high_urgency_case(session_id, urgency_level, detected_symptoms)

            web_context = web_rag_system.get_symptom_context(user_input, session.language)
            ai_response = self._generate_contextual_response(user_input, session, web_context)
            ai_response = response_quality_enhancer.enhance_response(ai_response, user_input, session.language, web_context)
            quality_metrics = response_quality_enhancer.evaluate_response_quality(ai_response, user_input, session.language)
            if quality_metrics.overall_score < 0.7:
                logging.warning(f"Session {session_id}: Low quality score={quality_metrics.overall_score:.2f} issues={quality_metrics.issues}")

            session.conversation_history.append({
                'role': 'assistant', 'content': ai_response,
                'timestamp': datetime.now().isoformat(), 'quality_score': quality_metrics.overall_score
            })

            if len(session.conversation_history) < 6:
                session.follow_up_questions = self.knowledge_base.generate_follow_up_questions(session.initial_symptoms, session.conversation_history)

            care_recommendation = self.knowledge_base.get_care_recommendation(session.urgency_level, specialist)
            session.recommended_action = care_recommendation['action']

            response = self._format_response(ai_response, session, care_recommendation)
            logging.info(f"Session {session_id}: Processed input, urgency={session.urgency_level}")
            return response
        except Exception as e:
            logging.error(f"Error processing user input: {str(e)}")
            return ("⚠️ An error occurred while processing your request. Please try again." if self.default_language == 'en' else "⚠️ Une erreur s'est produite lors du traitement de votre demande. Veuillez réessayer.")
    
    def _generate_contextual_response(self, user_input: str, session: PatientSession, web_context: str = "") -> str:
        """Generate AI response with conversation context, medical knowledge, and web RAG with structured sections"""
        try:
            conversation_context = ""
            if len(session.conversation_history) > 2:
                for exch in session.conversation_history[-4:]:
                    role = 'Patient' if exch['role'] == 'user' else 'Assistant'
                    conversation_context += f"{role}: {exch['content'][:300]}\n"

            system_instruction = self._get_enhanced_system_instruction(session.language)

            if session.language == 'fr':
                prompt = (
                    "CONTEXTE:\n" + conversation_context +
                    "\nSYMPTÔMES / QUESTION:\n" + user_input +
                    "\n\nRÉSUMÉ SOURCES FIABLES:\n" + web_context[:800] +
                    "\n\nFournir une réponse structurée en sections distinctes:\n"
                    "1. Résumé rapide\n2. Analyse clinique\n3. Facteurs de gravité potentiels\n4. Recommandation de prise en charge (niveau 1-5)\n5. Conseils de surveillance / prévention\n6. Question de clarification (si nécessaire)\n"
                    "Rester concis, clair, empathique. Aucune prescription."
                )
            else:
                prompt = (
                    "CONTEXT:\n" + conversation_context +
                    "\nSYMPTOMS / QUESTION:\n" + user_input +
                    "\n\nRELIABLE SOURCES SUMMARY:\n" + web_context[:800] +
                    "\n\nProvide a structured answer with sections:\n"
                    "1. Quick Summary\n2. Clinical Analysis\n3. Possible Red Flags\n4. Care Recommendation (level 1-5)\n5. Monitoring / Self-care Advice\n6. Clarifying Question (if needed)\n"
                    "Be concise, clear, empathetic. No prescriptions."
                )

            headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "HTTP-Referer": "BoCare-Medical-Assistant", "Content-Type": "application/json"}
            data = {"model": "mistralai/mistral-7b-instruct", "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}], "max_tokens": 550, "temperature": 0.65}
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                try:
                    return response.json()['choices'][0]['message']['content']
                except Exception as parse_err:
                    logging.error(f"Parse error: {parse_err}")
                    return ("Réponse incomplète reçue." if session.language == 'fr' else "Incomplete response received.")
            else:
                logging.error(f"API Error {response.status_code}: {response.text[:300]}")
                return ("Service indisponible momentanément." if session.language == 'fr' else "Service temporarily unavailable.")
        except Exception as e:
            logging.error(f"Error generating response: {str(e)}")
            return ("Erreur lors de la génération de réponse." if session.language == 'fr' else "Error generating response.")
    
    def _get_enhanced_system_instruction(self, language: str) -> str:
        """Get enhanced system instruction based on language"""
        if language == 'fr':
            return """Vous êtes BoCare, un assistant médical intelligent utilisant les dernières avancées en IA médicale et RAG (Retrieval Augmented Generation).

RÔLE PRINCIPAL:
- Analyser les symptômes avec précision et empathie en utilisant des sources médicales fiables
- Effectuer un triage intelligent pour orienter vers le niveau de soins approprié
- Détecter les urgences médicales et alerter immédiatement
- Fournir des informations médicales basées uniquement sur des sources autorisées

DIRECTIVES CRITIQUES DE SÉCURITÉ:
- Ne JAMAIS donner de diagnostic définitif
- Ne JAMAIS prescrire de médicaments
- TOUJOURS recommander une consultation médicale professionnelle
- Utiliser UNIQUEMENT les informations des sources médicales fournies
- En cas d'urgence, orienter immédiatement vers les services d'urgence
- Admettre les limites quand l'information est insuffisante

STYLE DE COMMUNICATION:
- Langage médical précis mais accessible
- Ton empathique et rassurant
- Questions ciblées pour clarifier les symptômes
- Réponses structurées avec triage clair
- Adaptation du ton selon le niveau d'urgence (1-5)"""
        else:
            return """You are BoCare, an intelligent medical assistant using the latest advances in medical AI and RAG (Retrieval Augmented Generation).

PRIMARY ROLE:
- Analyze symptoms with precision and empathy using reliable medical sources
- Perform intelligent triage to guide to appropriate level of care
- Detect medical emergencies and alert immediately
- Provide medical information based solely on authoritative sources

CRITICAL SAFETY DIRECTIVES:
- NEVER give definitive diagnosis
- NEVER prescribe medications
- ALWAYS recommend professional medical consultation
- Use ONLY information from provided medical sources
- In emergencies, immediately direct to emergency services
- Acknowledge limitations when information is insufficient

COMMUNICATION STYLE:
- Precise but accessible medical language
- Empathetic and reassuring tone
- Targeted questions to clarify symptoms
- Structured responses with clear triage
- Tone adaptation based on urgency level (1-5)"""
    
    def _format_response(self, ai_response: str, session: PatientSession, care_recommendation: Dict) -> str:
        """Format final response: structured sections, urgency banner, localized content, variation to avoid repetition"""
        lang = session.language
        header_variants_fr = ["💬 **Analyse médicale structurée:**", "🩺 **Évaluation clinique détaillée:**", "📋 **Résumé d'orientation médicale:**"]
        header_variants_en = ["💬 **Structured Medical Analysis:**", "🩺 **Detailed Clinical Evaluation:**", "📋 **Medical Guidance Summary:**"]
        header = random.choice(header_variants_fr if lang == 'fr' else header_variants_en)

        formatted_response = f"{header}\n{ai_response.strip()}\n\n"

        if session.urgency_level >= 4:
            formatted_response += ("🚨 **NIVEAU D'URGENCE ÉLEVÉ (" + str(session.urgency_level) + "/5)**\n" if lang == 'fr' else f"🚨 **HIGH URGENCY LEVEL ({session.urgency_level}/5)**\n")
        elif session.urgency_level >= 3:
            formatted_response += ("⚠️ **NIVEAU D'URGENCE MODÉRÉ (" + str(session.urgency_level) + "/5)**\n" if lang == 'fr' else f"⚠️ **MODERATE URGENCY LEVEL ({session.urgency_level}/5)**\n")
        else:
            formatted_response += ("ℹ️ **NIVEAU D'URGENCE FAIBLE (" + str(session.urgency_level) + "/5)**\n" if lang == 'fr' else f"ℹ️ **LOW URGENCY LEVEL ({session.urgency_level}/5)**\n")

        formatted_response += f"\n{care_recommendation['icon']} "
        if lang == 'fr':
            formatted_response += f"**RECOMMANDATION:**\n{care_recommendation['recommendation']}\n⏰ **Délai:** {care_recommendation['timeframe']}\n\n"
        else:
            recommendation_map = {
                'Appelez le 15 (SAMU) ou rendez-vous immédiatement aux urgences': 'Call emergency services or go to the ER immediately',
                'Consultez un médecin dans les prochaines heures': 'See a doctor within the next few hours',
                'Prenez rendez-vous avec un spécialiste sous 24-48h': 'Schedule a specialist within 24-48h',
                'Consultez votre médecin traitant dans les prochains jours': 'Consult your primary care doctor in the coming days',
                "Surveillez l'évolution, consultez si aggravation": 'Monitor progression, consult if worsening'
            }
            timeframe_map = {
                'Immédiatement': 'Immediately',
                'Dans les 2-6 heures': 'Within 2-6 hours',
                'Dans les 24-48 heures': 'Within 24-48 hours',
                'Dans les 2-7 jours': 'Within 2-7 days',
                'Surveillance, consultation si nécessaire': 'Monitor, consult if needed'
            }
            rec_en = care_recommendation['recommendation']
            for fr_text, en_text in recommendation_map.items():
                rec_en = rec_en.replace(fr_text, en_text)
            formatted_response += f"**RECOMMENDATION:**\n{rec_en}\n⏰ **Timeframe:** {timeframe_map.get(care_recommendation['timeframe'], care_recommendation['timeframe'])}\n\n"

        if session.follow_up_questions and len(session.conversation_history) < 6:
            if lang == 'fr':
                formatted_response += "❓ **Questions de suivi:**\n"
                for q in session.follow_up_questions:
                    formatted_response += f"• {q}\n"
            else:
                formatted_response += "❓ **Follow-up Questions:**\n"
                translation_map = {
                    'Sur une échelle de 1 à 10, comment évalueriez-vous votre douleur ?': 'On a scale of 1 to 10, how would you rate your pain?',
                    'La douleur est-elle constante ou intermittente ?': 'Is the pain constant or intermittent?',
                    'Qu\'est-ce qui améliore ou aggrave votre douleur ?': 'What makes the pain better or worse?',
                    'Depuis quand ressentez-vous ces symptômes ?': 'How long have you had these symptoms?',
                    'Les symptômes sont-ils apparus soudainement ou progressivement ?': 'Did the symptoms appear suddenly or gradually?',
                    'Avez-vous déjà eu des symptômes similaires auparavant ?': 'Have you had similar symptoms before?',
                    'Ressentez-vous d\'autres symptômes en même temps ?': 'Do you have other symptoms at the same time?',
                    'Avez-vous de la fièvre, des nausées ou des vertiges ?': 'Do you have fever, nausea, or dizziness?',
                    'Votre appétit ou votre sommeil sont-ils affectés ?': 'Is your appetite or sleep affected?',
                    'Prenez-vous actuellement des médicaments ?': 'Are you currently taking any medications?',
                    'Avez-vous des antécédents médicaux particuliers ?': 'Do you have any significant medical history?',
                    'Y a-t-il des allergies médicamenteuses à signaler ?': 'Do you have any drug allergies?'
                }
                for q in session.follow_up_questions:
                    formatted_response += f"• {translation_map.get(q, q)}\n"
            formatted_response += "\n"

        disclaimer_fr = "⚠️ **Important:** Cette analyse fournit une orientation préliminaire. Consultez toujours un professionnel de santé pour un diagnostic et un traitement adaptés."  # noqa
        disclaimer_en = "⚠️ **Important:** This analysis provides preliminary guidance. Always consult a healthcare professional for proper diagnosis and treatment."  # noqa
        formatted_response += (disclaimer_fr if lang == 'fr' else disclaimer_en)
        return formatted_response
    
    def get_session_summary(self, session_id: str) -> Optional[Dict]:
        """Get session summary for export or review"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            return session.to_dict()
        return None


# Legacy function for backward compatibility
def get_medical_response(symptoms):
    """Legacy function - now uses enhanced chatbot"""
    chatbot = EnhancedMedicalChatbot()
    return chatbot.process_user_input(symptoms)


# Global chatbot instance for UI
global_chatbot = EnhancedMedicalChatbot()
