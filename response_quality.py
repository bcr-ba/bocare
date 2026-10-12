"""
Response Quality Enhancer and Hallucination Detector
Improves medical response quality and detects AI hallucinations
"""
import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re
import logging

@dataclass
class QualityMetrics:
    """Response quality metrics"""
    coherence_score: float
    medical_accuracy_score: float
    safety_score: float
    completeness_score: float
    overall_score: float
    issues: List[str]
    suggestions: List[str]

class ResponseQualityEnhancer:
    """Enhances and validates AI response quality"""
    
    def __init__(self):
        self.medical_terms = {
            'en': [
                'symptom', 'symptoms', 'diagnosis', 'treatment', 'medication', 'doctor',
                'physician', 'hospital', 'clinic', 'pain', 'fever', 'headache',
                'nausea', 'vomiting', 'diarrhea', 'fatigue', 'dizziness', 'chest',
                'breathing', 'heart', 'blood', 'pressure', 'infection', 'inflammation'
            ],
            'fr': [
                'symptôme', 'symptômes', 'diagnostic', 'traitement', 'médicament', 'médecin',
                'docteur', 'hôpital', 'clinique', 'douleur', 'fièvre', 'mal de tête',
                'nausée', 'vomissement', 'diarrhée', 'fatigue', 'vertige', 'thorax',
                'respiration', 'cœur', 'sang', 'pression', 'infection', 'inflammation'
            ]
        }
        
        self.required_disclaimers = {
            'en': [
                'consult', 'healthcare professional', 'medical advice', 'doctor',
                'physician', 'emergency', 'seek help', 'professional help'
            ],
            'fr': [
                'consultez', 'professionnel de santé', 'conseil médical', 'médecin',
                'docteur', 'urgence', 'chercher aide', 'aide professionnelle'
            ]
        }
        
        self.hallucination_patterns = [
            r"i am (not )?able to",
            r"as an ai",
            r"i (can|cannot) provide",
            r"according to my (knowledge|training)",
            r"based on my (knowledge|training)",
            r"i don't have access to",
            r"i'm (just )?an ai",
            r"as a language model",
            r"je suis (une )?ia",
            r"en tant qu'ia",
            r"selon mes connaissances",
            r"je n'ai pas accès",
        ]
        
        self.logger = logging.getLogger(__name__)
    
    def enhance_response(self, response: str, user_query: str, language: str = 'en', medical_context: str = '') -> str:
        """Enhance response quality with medical context"""
        # Detect and fix hallucinations
        enhanced_response = self._fix_hallucinations(response, language)
        
        # Add medical context if missing
        enhanced_response = self._add_medical_context(enhanced_response, medical_context, language)
        
        # Ensure proper disclaimers
        enhanced_response = self._ensure_disclaimers(enhanced_response, language)
        
        # Add urgency assessment if needed
        enhanced_response = self._add_urgency_context(enhanced_response, user_query, language)
        
        return enhanced_response
    
    def evaluate_response_quality(self, response: str, user_query: str, language: str = 'en') -> QualityMetrics:
        """Evaluate response quality comprehensively"""
        issues = []
        suggestions = []
        
        # Check coherence
        coherence_score = self._check_coherence(response)
        if coherence_score < 0.7:
            issues.append("Response lacks coherence")
            suggestions.append("Improve response structure and flow")
        
        # Check medical accuracy indicators
        medical_score = self._check_medical_accuracy(response, language)
        if medical_score < 0.6:
            issues.append("Insufficient medical terminology or context")
            suggestions.append("Add more medical context and terminology")
        
        # Check safety
        safety_score = self._check_safety(response, language)
        if safety_score < 0.8:
            issues.append("Missing or insufficient safety disclaimers")
            suggestions.append("Add proper medical disclaimers and safety warnings")
        
        # Check completeness
        completeness_score = self._check_completeness(response, user_query)
        if completeness_score < 0.6:
            issues.append("Response may be incomplete")
            suggestions.append("Provide more comprehensive information")
        
        # Overall score
        overall_score = (coherence_score + medical_score + safety_score + completeness_score) / 4
        
        return QualityMetrics(
            coherence_score=coherence_score,
            medical_accuracy_score=medical_score,
            safety_score=safety_score,
            completeness_score=completeness_score,
            overall_score=overall_score,
            issues=issues,
            suggestions=suggestions
        )
    
    def _fix_hallucinations(self, response: str, language: str) -> str:
        """Detect meta-AI self references and replace with neutral medical phrasing in correct language"""
        original = response
        for pattern in self.hallucination_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                self.logger.warning(f"Hallucination/meta phrase detected: {pattern}")
                if language == 'en':
                    replacements = [
                        (r"as an ai[^.]*", "From available medical guidance"),
                        (r"as a language model[^.]*", "From reviewed medical sources"),
                        (r"i (can|cannot) provide[^.]*", "The information suggests"),
                        (r"according to my (knowledge|training)[^.]*", "Reliable medical sources indicate"),
                        (r"i'm (just )?an ai[^.]*", "")
                    ]
                else:
                    replacements = [
                        (r"en tant qu'ia[^.]*", "Selon des sources médicales fiables"),
                        (r"je suis (une )?ia[^.]*", ""),
                        (r"selon mes connaissances[^.]*", "Les sources médicales indiquent"),
                        (r"je n'ai pas accès[^.]*", ""),
                        (r"je (peux|ne peux pas) fournir[^.]*", "Les données disponibles suggèrent")
                    ]
                for pat, repl in replacements:
                    response = re.sub(pat, repl, response, flags=re.IGNORECASE)
        if original != response:
            # Cleanup double spaces after removals
            response = re.sub(r"\s{2,}", " ", response).strip()
        return response
    
    def _add_medical_context(self, response: str, medical_context: str, language: str) -> str:
        """Append concise medical context snippet (deduplicated)"""
        if not medical_context or len(medical_context) < 50:
            return response
        snippet_len = 360
        snippet = medical_context[:snippet_len] + ("..." if len(medical_context) > snippet_len else "")
        if snippet in response:
            return response
        intro = "\n\n**Medical Context (trusted sources):**\n" if language == 'en' else "\n\n**Contexte médical (sources fiables):**\n"
        return response + intro + snippet
    
    def _ensure_disclaimers(self, response: str, language: str) -> str:
        """Ensure proper medical disclaimers"""
        disclaimer_terms = self.required_disclaimers[language]
        has_disclaimer = any(term in response.lower() for term in disclaimer_terms)
        
        if not has_disclaimer:
            if language == 'en':
                disclaimer = "\n\n⚠️ **Important:** Preliminary guidance only. Consult a healthcare professional for diagnosis and treatment."
            else:
                disclaimer = "\n\n⚠️ **Important:** Orientation préliminaire uniquement. Consultez un professionnel de santé pour un diagnostic et un traitement."
            response += disclaimer
        
        return response
    
    def _add_urgency_context(self, response: str, user_query: str, language: str) -> str:
        """Add urgency context based on symptoms"""
        emergency_indicators = [
            'chest pain', 'difficulty breathing', 'unconscious', 'severe bleeding',
            'douleur thoracique', 'difficulté respiratoire', 'inconscient', 'saignement sévère'
        ]
        
        query_lower = user_query.lower()
        has_emergency = any(indicator in query_lower for indicator in emergency_indicators)
        
        if has_emergency and '🚨' not in response:
            if language == 'en':
                urgency_note = "\n\n🚨 **URGENT:** If you're experiencing severe symptoms, seek immediate medical attention or call emergency services!"
            else:
                urgency_note = "\n\n🚨 **URGENT:** Si vous ressentez des symptômes graves, consultez immédiatement un médecin ou appelez les services d'urgence!"
            
            response = urgency_note + "\n\n" + response
        
        return response
    
    def _check_coherence(self, response: str) -> float:
        """Check response coherence"""
        sentences = response.split('.')
        if len(sentences) < 2:
            return 0.5
        
        # Simple coherence check based on length and structure
        avg_sentence_length = sum(len(s.strip()) for s in sentences) / len(sentences)
        
        if avg_sentence_length < 10:
            return 0.3
        elif avg_sentence_length > 200:
            return 0.6
        else:
            return 0.8
    
    def _check_medical_accuracy(self, response: str, language: str) -> float:
        """Check medical accuracy indicators"""
        medical_terms = self.medical_terms[language]
        response_lower = response.lower()
        
        medical_term_count = sum(1 for term in medical_terms if term in response_lower)
        term_density = medical_term_count / len(response.split()) if response.split() else 0
        
        # Score based on medical term density
        if term_density > 0.1:
            return 0.9
        elif term_density > 0.05:
            return 0.7
        elif term_density > 0.02:
            return 0.5
        else:
            return 0.3
    
    def _check_safety(self, response: str, language: str) -> float:
        """Check safety disclaimers and warnings"""
        disclaimer_terms = self.required_disclaimers[language]
        response_lower = response.lower()
        
        disclaimer_count = sum(1 for term in disclaimer_terms if term in response_lower)
        
        if disclaimer_count >= 2:
            return 1.0
        elif disclaimer_count == 1:
            return 0.7
        else:
            return 0.3
    
    def _check_completeness(self, response: str, user_query: str) -> float:
        """Check response completeness"""
        response_length = len(response.split())
        query_length = len(user_query.split())
        
        # Expect response to be proportional to query complexity
        expected_length = max(50, query_length * 5)
        
        if response_length >= expected_length:
            return 1.0
        elif response_length >= expected_length * 0.7:
            return 0.8
        elif response_length >= expected_length * 0.4:
            return 0.6
        else:
            return 0.3

# Global instance
response_quality_enhancer = ResponseQualityEnhancer()
