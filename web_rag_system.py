"""
Enhanced Web-Based RAG System for Medical Information Retrieval
Retrieves real-time medical information from authoritative sources
"""
import requests
from bs4 import BeautifulSoup
import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import time
from urllib.parse import quote_plus
import json

@dataclass
class MedicalSource:
    """Medical information source"""
    name: str
    url: str
    content: str
    reliability_score: float
    last_updated: str

class WebRAGSystem:
    """Web-based Retrieval Augmented Generation system"""
    
    def __init__(self):
        self.medical_sources = {
            'mayo_clinic': 'https://www.mayoclinic.org',
            'webmd': 'https://www.webmd.com',
            'medlineplus': 'https://medlineplus.gov',
            'healthline': 'https://www.healthline.com',
            'nhs': 'https://www.nhs.uk'
        }
        
        self.headers = {
            'User-Agent': 'BoCare Medical Assistant Bot 1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        self.cache = {}  # Simple in-memory cache
        self.cache_duration = 3600  # 1 hour
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def search_medical_information(self, query: str, language: str = 'en') -> List[MedicalSource]:
        """Search for medical information from multiple sources"""
        # Check cache first
        cache_key = f"{query}_{language}"
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        sources = []
        
        try:
            # Search Mayo Clinic
            mayo_results = self._search_mayo_clinic(query)
            if mayo_results:
                sources.extend(mayo_results)
            
            # Search MedlinePlus
            medline_results = self._search_medlineplus(query)
            if medline_results:
                sources.extend(medline_results)
            
            # Search NHS (for English queries)
            if language == 'en':
                nhs_results = self._search_nhs(query)
                if nhs_results:
                    sources.extend(nhs_results)
            
            # Search French sources for French queries
            if language == 'fr':
                french_results = self._search_french_sources(query)
                if french_results:
                    sources.extend(french_results)
            
        except Exception as e:
            self.logger.error(f"Error searching medical information: {str(e)}")
        
        # Sort by reliability score
        sources.sort(key=lambda x: x.reliability_score, reverse=True)
        
        # Cache results
        self.cache[cache_key] = (sources[:5], time.time())  # Keep top 5 results
        
        return sources[:5]
    
    def _search_mayo_clinic(self, query: str) -> List[MedicalSource]:
        """Search Mayo Clinic for medical information"""
        try:
            search_url = f"https://www.mayoclinic.org/search/search-results?q={quote_plus(query)}"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                sources = []
                
                # Extract search results
                results = soup.find_all('div', class_='search-result')[:3]  # Top 3 results
                
                for result in results:
                    title_elem = result.find('h3')
                    if title_elem:
                        title = title_elem.get_text().strip()
                        link_elem = result.find('a')
                        
                        if link_elem:
                            url = link_elem.get('href')
                            if not url.startswith('http'):
                                url = f"https://www.mayoclinic.org{url}"
                            
                            # Get content from the page
                            content = self._extract_page_content(url)
                            
                            if content:
                                sources.append(MedicalSource(
                                    name=f"Mayo Clinic - {title}",
                                    url=url,
                                    content=content,
                                    reliability_score=0.95,  # High reliability
                                    last_updated=time.strftime("%Y-%m-%d")
                                ))
                
                return sources
        
        except Exception as e:
            self.logger.error(f"Error searching Mayo Clinic: {str(e)}")
            return []
    
    def _search_medlineplus(self, query: str) -> List[MedicalSource]:
        """Search MedlinePlus for medical information"""
        try:
            search_url = f"https://medlineplus.gov/search/?query={quote_plus(query)}"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                sources = []
                
                # Extract search results
                results = soup.find_all('div', class_='search-result')[:2]  # Top 2 results
                
                for result in results:
                    title_elem = result.find('h2')
                    if title_elem:
                        title = title_elem.get_text().strip()
                        link_elem = title_elem.find('a')
                        
                        if link_elem:
                            url = link_elem.get('href')
                            if not url.startswith('http'):
                                url = f"https://medlineplus.gov{url}"
                            
                            # Get summary from search result
                            summary_elem = result.find('p')
                            content = summary_elem.get_text().strip() if summary_elem else ""
                            
                            sources.append(MedicalSource(
                                name=f"MedlinePlus - {title}",
                                url=url,
                                content=content,
                                reliability_score=0.90,  # High reliability
                                last_updated=time.strftime("%Y-%m-%d")
                            ))
                
                return sources
        
        except Exception as e:
            self.logger.error(f"Error searching MedlinePlus: {str(e)}")
            return []
    
    def _search_nhs(self, query: str) -> List[MedicalSource]:
        """Search NHS for medical information"""
        try:
            search_url = f"https://www.nhs.uk/search/?q={quote_plus(query)}"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                sources = []
                
                # Extract search results
                results = soup.find_all('article', class_='search-results__item')[:2]
                
                for result in results:
                    title_elem = result.find('h2')
                    if title_elem:
                        title = title_elem.get_text().strip()
                        link_elem = title_elem.find('a')
                        
                        if link_elem:
                            url = link_elem.get('href')
                            if not url.startswith('http'):
                                url = f"https://www.nhs.uk{url}"
                            
                            # Get summary
                            summary_elem = result.find('p')
                            content = summary_elem.get_text().strip() if summary_elem else ""
                            
                            sources.append(MedicalSource(
                                name=f"NHS - {title}",
                                url=url,
                                content=content,
                                reliability_score=0.92,  # Very high reliability
                                last_updated=time.strftime("%Y-%m-%d")
                            ))
                
                return sources
        
        except Exception as e:
            self.logger.error(f"Error searching NHS: {str(e)}")
            return []
    
    def _search_french_sources(self, query: str) -> List[MedicalSource]:
        """Search French medical sources"""
        try:
            # Search Ameli.fr (French health insurance)
            search_url = f"https://www.ameli.fr/recherche?text={quote_plus(query)}"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            
            sources = []
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract basic information for French sources
                results = soup.find_all('div', class_='search-result')[:2]
                
                for result in results:
                    title_elem = result.find('h3')
                    if title_elem:
                        title = title_elem.get_text().strip()
                        content = "Information médicale en français - consultez le lien pour plus de détails"
                        
                        sources.append(MedicalSource(
                            name=f"Ameli.fr - {title}",
                            url="https://www.ameli.fr",
                            content=content,
                            reliability_score=0.88,
                            last_updated=time.strftime("%Y-%m-%d")
                        ))
            
            return sources
            
        except Exception as e:
            self.logger.error(f"Error searching French sources: {str(e)}")
            return []
    
    def _extract_page_content(self, url: str) -> str:
        """Extract relevant content from a medical page"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Extract main content
                main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
                
                if main_content:
                    text = main_content.get_text()
                    # Clean up the text
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = ' '.join(chunk for chunk in chunks if chunk)
                    
                    # Limit content length
                    return text[:1000] + "..." if len(text) > 1000 else text
            
            return ""
            
        except Exception as e:
            self.logger.error(f"Error extracting content from {url}: {str(e)}")
            return ""
    
    def get_symptom_context(self, symptoms: str, language: str = 'en') -> str:
        """Get contextual medical information for symptoms"""
        sources = self.search_medical_information(symptoms, language)
        
        if not sources:
            return "No reliable medical information found for the given symptoms."
        
        context = "MEDICAL CONTEXT FROM AUTHORITATIVE SOURCES:\n\n"
        
        for i, source in enumerate(sources, 1):
            context += f"{i}. {source.name} (Reliability: {source.reliability_score:.0%}):\n"
            context += f"   {source.content[:300]}...\n"
            context += f"   Source: {source.url}\n\n"
        
        return context
    
    def validate_medical_response(self, response: str, original_query: str) -> Dict[str, any]:
        """Validate AI response against retrieved medical information"""
        # Basic validation - check for medical disclaimers and emergency warnings
        validation_result = {
            'has_disclaimer': False,
            'has_emergency_warning': False,
            'mentions_consultation': False,
            'quality_score': 0.0
        }
        
        response_lower = response.lower()
        
        # Check for medical disclaimer
        disclaimer_phrases = [
            'consult', 'healthcare professional', 'medical advice', 'doctor',
            'consultez', 'professionnel de santé', 'conseil médical', 'médecin'
        ]
        
        validation_result['has_disclaimer'] = any(phrase in response_lower for phrase in disclaimer_phrases)
        
        # Check for emergency warnings
        emergency_phrases = ['emergency', 'urgent', 'immediately', 'urgence', 'immédiatement']
        validation_result['has_emergency_warning'] = any(phrase in response_lower for phrase in emergency_phrases)
        
        # Check consultation recommendation
        consult_phrases = ['see a doctor', 'visit', 'appointment', 'rendez-vous', 'voir un médecin']
        validation_result['mentions_consultation'] = any(phrase in response_lower for phrase in consult_phrases)
        
        # Calculate quality score
        score = 0.0
        if validation_result['has_disclaimer']:
            score += 0.4
        if validation_result['mentions_consultation']:
            score += 0.3
        if len(response) > 100:  # Sufficient detail
            score += 0.3
        
        validation_result['quality_score'] = score
        
        return validation_result

# Global instance
web_rag_system = WebRAGSystem()
