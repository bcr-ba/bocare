"""
Medical Knowledge Base for Enhanced Chatbot
Contains medical data structures, symptom analysis, and triage logic
"""
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import re

@dataclass
class SymptomProfile:
    """Structure for symptom information"""
    name: str
    severity_indicators: List[str]
    associated_symptoms: List[str]
    urgency_score: int  # 1-5 scale
    specialist_referral: Optional[str] = None

@dataclass
class PatientSession:
    """Patient consultation session data"""
    session_id: str
    initial_symptoms: List[str]
    conversation_history: List[Dict[str, str]]
    follow_up_questions: List[str]
    responses: Dict[str, str]
    urgency_level: int
    recommended_action: str
    timestamp: datetime
    language: str = 'fr'
    
    def to_dict(self):
        return asdict(self)

class MedicalKnowledgeBase:
    """Enhanced medical knowledge system with RAG capabilities"""
    
    def __init__(self):
        self.symptom_profiles = self._load_symptom_profiles()
        self.urgency_keywords = self._load_urgency_keywords()
        self.follow_up_templates = self._load_follow_up_templates()
        self.care_paths = self._load_care_paths()
    
    def _load_symptom_profiles(self) -> Dict[str, SymptomProfile]:
        """Load comprehensive symptom database"""
        return {
            "chest_pain": SymptomProfile(
                name="chest_pain",
                severity_indicators=["crushing pain", "radiating pain", "shortness of breath", "nausea"],
                associated_symptoms=["sweating", "dizziness", "arm pain", "jaw pain"],
                urgency_score=5,
                specialist_referral="cardiologue"
            ),
            "headache": SymptomProfile(
                name="headache",
                severity_indicators=["sudden severe", "worst headache", "vision changes", "confusion"],
                associated_symptoms=["nausea", "vomiting", "light sensitivity", "neck stiffness"],
                urgency_score=3,
                specialist_referral="neurologue"
            ),
            "fever": SymptomProfile(
                name="fever",
                severity_indicators=["high fever >39°C", "persistent fever", "difficulty breathing"],
                associated_symptoms=["chills", "sweating", "weakness", "body aches"],
                urgency_score=2
            ),
            "abdominal_pain": SymptomProfile(
                name="abdominal_pain",
                severity_indicators=["severe pain", "persistent pain", "vomiting blood"],
                associated_symptoms=["nausea", "vomiting", "constipation", "diarrhea"],
                urgency_score=3,
                specialist_referral="gastroentérologue"
            ),
            "skin_rash": SymptomProfile(
                name="skin_rash",
                severity_indicators=["rapid spreading", "difficulty breathing", "swelling"],
                associated_symptoms=["itching", "burning", "blisters", "scaling"],
                urgency_score=2,
                specialist_referral="dermatologue"
            )
        }
    
    def _load_urgency_keywords(self) -> Dict[str, int]:
        """Keywords that indicate different urgency levels"""
        return {
            # Emergency keywords (5)
            "chest pain": 5, "crushing pain": 5, "can't breathe": 5, "unconscious": 5,
            "severe bleeding": 5, "stroke": 5, "heart attack": 5,
            "douleur thoracique": 5, "ne peut pas respirer": 5, "inconscient": 5,
            "saignement sévère": 5, "avc": 5, "crise cardiaque": 5,
            
            # High urgency (4)
            "severe pain": 4, "high fever": 4, "persistent vomiting": 4,
            "douleur sévère": 4, "fièvre élevée": 4, "vomissements persistants": 4,
            
            # Moderate urgency (3)
            "persistent": 3, "worsening": 3, "spreading": 3,
            "persistant": 3, "s'aggrave": 3, "se propage": 3,
            
            # Low urgency (1-2)
            "mild": 1, "occasional": 1, "slight": 2,
            "léger": 1, "occasionnel": 1, "faible": 2
        }
    
    def _load_follow_up_templates(self) -> Dict[str, List[str]]:
        """Templates for intelligent follow-up questions"""
        return {
            "pain_assessment": [
                "Sur une échelle de 1 à 10, comment évalueriez-vous votre douleur ?",
                "La douleur est-elle constante ou intermittente ?",
                "Qu'est-ce qui améliore ou aggrave votre douleur ?"
            ],
            "symptom_duration": [
                "Depuis quand ressentez-vous ces symptômes ?",
                "Les symptômes sont-ils apparus soudainement ou progressivement ?",
                "Avez-vous déjà eu des symptômes similaires auparavant ?"
            ],
            "associated_symptoms": [
                "Ressentez-vous d'autres symptômes en même temps ?",
                "Avez-vous de la fièvre, des nausées ou des vertiges ?",
                "Votre appétit ou votre sommeil sont-ils affectés ?"
            ],
            "medical_history": [
                "Prenez-vous actuellement des médicaments ?",
                "Avez-vous des antécédents médicaux particuliers ?",
                "Y a-t-il des allergies médicamenteuses à signaler ?"
            ]
        }
    
    def _load_care_paths(self) -> Dict[int, Dict[str, str]]:
        """Care path recommendations based on urgency level"""
        return {
            5: {
                "action": "🚨 URGENCE IMMÉDIATE",
                "recommendation": "Appelez le 15 (SAMU) ou rendez-vous immédiatement aux urgences",
                "timeframe": "Immédiatement",
                "icon": "🚨"
            },
            4: {
                "action": "⚡ CONSULTATION URGENTE",
                "recommendation": "Consultez un médecin dans les prochaines heures",
                "timeframe": "Dans les 2-6 heures",
                "icon": "⚡"
            },
            3: {
                "action": "🏥 CONSULTATION SPÉCIALISÉE",
                "recommendation": "Prenez rendez-vous avec un spécialiste sous 24-48h",
                "timeframe": "Dans les 24-48 heures",
                "icon": "🏥"
            },
            2: {
                "action": "👨‍⚕️ MÉDECIN GÉNÉRALISTE",
                "recommendation": "Consultez votre médecin traitant dans les prochains jours",
                "timeframe": "Dans les 2-7 jours",
                "icon": "👨‍⚕️"
            },
            1: {
                "action": "💊 SURVEILLANCE",
                "recommendation": "Surveillez l'évolution, consultez si aggravation",
                "timeframe": "Surveillance, consultation si nécessaire",
                "icon": "💊"
            }
        }
    
    def analyze_symptoms(self, symptoms_text: str) -> Tuple[List[str], int, str]:
        """Analyze symptoms and determine urgency level"""
        symptoms_text_lower = symptoms_text.lower()
        detected_symptoms = []
        max_urgency = 1
        specialist = None
        
        # Detect known symptoms
        for symptom_key, profile in self.symptom_profiles.items():
            if any(indicator.lower() in symptoms_text_lower for indicator in profile.severity_indicators):
                detected_symptoms.append(symptom_key)
                max_urgency = max(max_urgency, profile.urgency_score)
                if profile.specialist_referral:
                    specialist = profile.specialist_referral
        
        # Check urgency keywords
        for keyword, urgency in self.urgency_keywords.items():
            if keyword.lower() in symptoms_text_lower:
                max_urgency = max(max_urgency, urgency)
        
        return detected_symptoms, max_urgency, specialist
    
    def generate_follow_up_questions(self, symptoms: List[str], conversation_history: List[Dict]) -> List[str]:
        """Generate intelligent follow-up questions based on context"""
        asked_categories = set()
        for exchange in conversation_history:
            if exchange.get('type') == 'question':
                # Determine which category this question belongs to
                question_text = exchange.get('content', '').lower()
                if any(word in question_text for word in ['douleur', 'pain', 'échelle']):
                    asked_categories.add('pain_assessment')
                elif any(word in question_text for word in ['depuis', 'when', 'duration']):
                    asked_categories.add('symptom_duration')
        
        # Select appropriate questions
        questions = []
        for category, question_list in self.follow_up_templates.items():
            if category not in asked_categories and len(questions) < 3:
                questions.extend(question_list[:1])  # Add one question per category
        
        return questions[:3]  # Limit to 3 questions
    
    def get_care_recommendation(self, urgency_level: int, specialist: Optional[str] = None) -> Dict[str, str]:
        """Get care path recommendation"""
        base_recommendation = self.care_paths.get(urgency_level, self.care_paths[1])
        
        if specialist and urgency_level >= 3:
            base_recommendation = base_recommendation.copy()
            base_recommendation["specialist"] = specialist
            base_recommendation["recommendation"] += f" (Spécialiste recommandé: {specialist})"
        
        return base_recommendation
