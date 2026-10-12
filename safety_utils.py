"""
Enhanced security and safety utilities for medical chatbot
Includes jailbreak detection, injection prevention, and hallucination mitigation
"""
import re
import logging
import hashlib
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
import time

@dataclass
class ValidationResult:
    """Result of input validation"""
    is_valid: bool
    error_message: Optional[str] = None
    warning_message: Optional[str] = None
    sanitized_input: Optional[str] = None

class AdvancedSecurityValidator:
    """Advanced security validator with jailbreak detection and injection prevention"""
    
    def __init__(self):
        self.jailbreak_patterns = [
            # Common jailbreak attempts
            r"ignore.{0,20}(previous|above|system|instruction)",
            r"forget.{0,20}(everything|previous|above|instruction)",
            r"act.{0,20}as.{0,20}(if|though)",
            r"pretend.{0,20}(to|that|you)",
            r"roleplay.{0,20}as",
            r"simulate.{0,20}(being|a)",
            r"override.{0,20}(safety|security|protocol)",
            r"disable.{0,20}(safety|security|filter)",
            r"\\[SYSTEM\\]|\\[ADMIN\\]|\\[ROOT\\]",
            r"sudo|administrator|admin.{0,10}mode",
            r"developer.{0,10}mode|debug.{0,10}mode",
            r"bypass.{0,20}(restriction|limit|safety)",
            r"jailbreak|jail.{0,5}break",
        ]
        
        self.prompt_injection_patterns = [
            r"\\n\\n.*?(user|human|assistant):",
            r"<\\|.*?\\|>",
            r"\\[\\[.*?\\]\\]",
            r"{{.*?}}",
            r"```.*?```",
            r"---.*?---",
            r"###.*?###",
        ]
        
        self.hallucination_indicators = [
            r"i am (not |un)?able to",
            r"as an ai",
            r"i (can|cannot) provide",
            r"according to my knowledge",
            r"based on my training",
        ]
        
        self.rate_limits = {}  # IP-based rate limiting
        self.max_requests_per_minute = 10

class MedicalInputValidator:
    """Enhanced medical input validation with security features"""
    
    def __init__(self):
        self.security_validator = AdvancedSecurityValidator()
        
        self.emergency_keywords = [
            # French emergency keywords
            "ne peut pas respirer", "difficulté respiratoire", "douleur thoracique intense",
            "perte de conscience", "saignement abondant", "convulsions", "paralysie",
            "crise cardiaque", "avc", "empoisonnement", "surdose",
            
            # English emergency keywords
            "can't breathe", "chest pain", "unconscious", "severe bleeding",
            "seizure", "paralysis", "heart attack", "stroke", "poisoning", "overdose"
        ]
        
        self.inappropriate_content = [
            "suicide", "self-harm", "violence", "drug abuse", "illegal",
            "suicide", "automutilation", "violence", "drogue", "illégal"
        ]
        
        self.medication_requests = [
            "prescription", "médicament", "medicine", "drug", "dosage",
            "ordonnance", "dose", "traitement"
        ]
    
    def validate_input(self, user_input: str, session_id: str = None) -> ValidationResult:
        """Comprehensive input validation with security checks"""
        if not user_input or len(user_input.strip()) < 2:
            return ValidationResult(
                is_valid=False,
                error_message="Please provide more details about your symptoms." if self._is_english(user_input) else "Veuillez fournir plus de détails sur vos symptômes."
            )
        
        # Rate limiting check
        if session_id and not self._check_rate_limit(session_id):
            return ValidationResult(
                is_valid=False,
                error_message="Too many requests. Please wait before sending another message." if self._is_english(user_input) else "Trop de requêtes. Veuillez attendre avant d'envoyer un autre message."
            )
        
        # Security validation
        security_check = self._validate_security(user_input)
        if not security_check['is_safe']:
            return ValidationResult(
                is_valid=False,
                error_message=security_check['message']
            )
        
        # Check input length
        if len(user_input) > 2000:
            return ValidationResult(
                is_valid=False,
                error_message="Your message is too long. Please shorten it." if self._is_english(user_input) else "Votre message est trop long. Veuillez le raccourcir."
            )
        
        # Sanitize input
        sanitized = self._sanitize_input(user_input)
        
        # Check for emergency keywords
        emergency_detected = self._detect_emergency(sanitized)
        if emergency_detected:
            return ValidationResult(
                is_valid=True,
                warning_message="⚠️ URGENT: If this is a medical emergency, call 911 immediately!" if self._is_english(user_input) else "⚠️ URGENT: Si c'est une urgence médicale, appelez le 15 (SAMU) immédiatement!",
                sanitized_input=sanitized
            )
        
        # Check for inappropriate content
        if self._contains_inappropriate_content(sanitized):
            return ValidationResult(
                is_valid=False,
                error_message="This type of content is not appropriate for a medical assistant." if self._is_english(user_input) else "Ce type de contenu n'est pas approprié pour un assistant médical."
            )
        
        # Check for medication requests
        if self._contains_medication_request(sanitized):
            return ValidationResult(
                is_valid=True,
                warning_message="⚠️ I cannot prescribe medications. Please consult a doctor." if self._is_english(user_input) else "⚠️ Je ne peux pas prescrire de médicaments. Consultez un médecin.",
                sanitized_input=sanitized
            )
        
        return ValidationResult(
            is_valid=True,
            sanitized_input=sanitized
        )
    
    def _sanitize_input(self, text: str) -> str:
        """Sanitize user input"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove potentially harmful characters
        text = re.sub(r'[<>{}[\]\\]', '', text)
        
        # Limit consecutive punctuation
        text = re.sub(r'[.!?]{3,}', '...', text)
        
        return text
    
    def _detect_emergency(self, text: str) -> bool:
        """Detect emergency situations"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.emergency_keywords)
    
    def _contains_inappropriate_content(self, text: str) -> bool:
        """Check for inappropriate content"""
        text_lower = text.lower()
        return any(word in text_lower for word in self.inappropriate_content)
    
    def _contains_medication_request(self, text: str) -> bool:
        """Check for medication/prescription requests"""
        text_lower = text.lower()
        return any(word in text_lower for word in self.medication_requests)
    
    def _validate_security(self, text: str) -> Dict[str, any]:
        """Advanced security validation"""
        text_lower = text.lower()
        
        # Check for jailbreak attempts
        for pattern in self.security_validator.jailbreak_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return {
                    'is_safe': False,
                    'message': "Security violation detected. Please ask legitimate medical questions only." if self._is_english(text) else "Violation de sécurité détectée. Veuillez poser uniquement des questions médicales légitimes."
                }
        
        # Check for prompt injection
        for pattern in self.security_validator.prompt_injection_patterns:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                return {
                    'is_safe': False,
                    'message': "Invalid input format detected. Please use plain text for medical questions." if self._is_english(text) else "Format d'entrée invalide détecté. Veuillez utiliser du texte simple pour les questions médicales."
                }
        
        return {'is_safe': True}
    
    def _check_rate_limit(self, session_id: str) -> bool:
        """Check rate limiting for session"""
        current_time = time.time()
        session_hash = hashlib.md5(session_id.encode()).hexdigest()
        
        if session_hash not in self.security_validator.rate_limits:
            self.security_validator.rate_limits[session_hash] = []
        
        # Clean old requests (older than 1 minute)
        self.security_validator.rate_limits[session_hash] = [
            timestamp for timestamp in self.security_validator.rate_limits[session_hash]
            if current_time - timestamp < 60
        ]
        
        # Check if under limit
        if len(self.security_validator.rate_limits[session_hash]) >= self.security_validator.max_requests_per_minute:
            return False
        
        # Add current request
        self.security_validator.rate_limits[session_hash].append(current_time)
        return True
    
    def _is_english(self, text: str) -> bool:
        """Simple language detection"""
        english_words = ['the', 'and', 'is', 'in', 'to', 'of', 'a', 'that', 'have', 'i', 'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at']
        french_words = ['le', 'de', 'et', 'à', 'un', 'il', 'être', 'et', 'en', 'avoir', 'que', 'pour', 'dans', 'ce', 'son', 'une', 'sur', 'avec', 'ne', 'se']
        
        text_lower = text.lower()
        english_count = sum(1 for word in english_words if word in text_lower)
        french_count = sum(1 for word in french_words if word in text_lower)
        
        return english_count > french_count

class SafetyMonitor:
    """Monitor and log safety-related events"""
    
    def __init__(self):
        self.logger = logging.getLogger("SafetyMonitor")
        
    def log_emergency_detection(self, session_id: str, user_input: str):
        """Log emergency situation detection"""
        self.logger.warning(f"EMERGENCY DETECTED - Session: {session_id}, Input: {user_input[:100]}...")
    
    def log_inappropriate_content(self, session_id: str, user_input: str):
        """Log inappropriate content attempt"""
        self.logger.warning(f"INAPPROPRIATE CONTENT - Session: {session_id}, Input: {user_input[:100]}...")
    
    def log_medication_request(self, session_id: str, user_input: str):
        """Log medication prescription request"""
        self.logger.info(f"MEDICATION REQUEST - Session: {session_id}, Input: {user_input[:100]}...")
    
    def log_high_urgency_case(self, session_id: str, urgency_level: int, symptoms: List[str]):
        """Log high urgency medical cases"""
        self.logger.warning(f"HIGH URGENCY CASE - Session: {session_id}, Level: {urgency_level}, Symptoms: {symptoms}")

# Global instances
input_validator = MedicalInputValidator()
safety_monitor = SafetyMonitor()
