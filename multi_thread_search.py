import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Set, Optional, Tuple
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from pathlib import Path
import sys
import signal
from collections import defaultdict
import hashlib
import pickle
import psutil
from functools import lru_cache

from domain_hunter import DomainHunter

ACCESS_KEY_ID = 'your_access_key_id'
ACCESS_KEY_SECRET = 'your_access_key_secret'

CHECKED_DOMAINS_FILE = 'checked_domains.json'
PREMIUM_RESULTS_FILE = 'premium_results.json'
AVAILABLE_DOMAINS_FILE = 'available_domains.json'
CONFIG_FILE = 'search_config.json'

MAX_WORKERS = 5
BASE_DELAY = 0.8
MAX_RETRIES = 5
SAVE_INTERVAL = 50


@dataclass
class DomainResult:
    domain: str
    available: bool
    price: Optional[float]
    check_time: str
    scores: Optional[Dict] = None
    profit_estimate: Optional[Dict] = None


@dataclass
class SearchStats:
    total_checked: int = 0
    available: int = 0
    premium: int = 0
    registered: int = 0
    no_price: int = 0
    errors: int = 0
    throttled: int = 0
    cache_hits: int = 0
    start_time: float = 0
    peak_memory_mb: float = 0
    avg_response_time: float = 0
    response_times: list = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        stats_dict = asdict(self)
        stats_dict.pop('response_times', None)
        return stats_dict
    
    def record_response_time(self, response_time: float):
        self.response_times.append(response_time)
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-1000:]
        self.avg_response_time = sum(self.response_times) / len(self.response_times)
    
    def print_summary(self, elapsed: float):
        rate = self.total_checked / elapsed if elapsed > 0 else 0
        cache_hit_rate = (self.cache_hits / self.total_checked * 100) if self.total_checked > 0 else 0
        
        print("\n" + "="*80)
        print("掃描統計")
        print("="*80)
        print(f"總檢查域名: {self.total_checked}")
        print(f"可購買域名: {self.available}")
        print(f"精品域名: {self.premium}")
        print(f"已註冊: {self.registered}")
        print(f"無價格: {self.no_price}")
        print(f"錯誤次數: {self.errors}")
        print(f"限流次數: {self.throttled}")
        print(f"緩存命中: {self.cache_hits} ({cache_hit_rate:.1f}%)")
        print(f"平均響應: {self.avg_response_time:.3f}秒")
        print(f"峰值內存: {self.peak_memory_mb:.1f} MB")
        print(f"總耗時: {elapsed/60:.1f} 分鐘")
        print(f"平均速度: {rate:.2f} 域名/秒")
        print("="*80)


class DomainCache:
    """智能域名緩存系統"""
    
    def __init__(self, cache_file: str = "domain_cache.pkl", max_age: int = 86400):
        self.cache_file = Path(cache_file)
        self.max_age = max_age
        self.cache: Dict[str, Tuple[DomainResult, float]] = {}
        self.load_cache()
    
    def load_cache(self):
        """加載緩存"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    self.cache = pickle.load(f)
                self._clean_expired()
                print(f"✓ 已加載緩存: {len(self.cache)} 條記錄")
            except Exception as e:
                print(f"⚠️ 加載緩存失敗: {e}")
                self.cache = {}
    
    def save_cache(self):
        """保存緩存"""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
        except Exception as e:
            print(f"⚠️ 保存緩存失敗: {e}")
    
    def _clean_expired(self):
        """清理過期緩存"""
        current_time = time.time()
        expired = [k for k, (_, timestamp) in self.cache.items() 
                  if current_time - timestamp > self.max_age]
        for key in expired:
            del self.cache[key]
        if expired:
            print(f"✓ 已清理 {len(expired)} 條過期緩存")
    
    def get(self, domain: str) -> Optional[DomainResult]:
        """獲取緩存"""
        if domain in self.cache:
            result, timestamp = self.cache[domain]
            if time.time() - timestamp <= self.max_age:
                return result
            else:
                del self.cache[domain]
        return None
    
    def set(self, domain: str, result: DomainResult):
        """設置緩存"""
        self.cache[domain] = (result, time.time())
    
    def clear(self):
        """清空緩存"""
        self.cache = {}
        if self.cache_file.exists():
            self.cache_file.unlink()


class AdvancedDomainScorer:
    """增強域名評分系統 - SEO、品牌價值、市場趨勢"""
    
    def __init__(self):
        self.premium_keywords = {
            'tier1': ['ai', 'pay', 'bank', 'shop', 'nft', 'crypto', 'defi', 'web3'],
            'tier2': ['tech', 'cloud', 'finance', 'trade', 'saas', 'api', 'meta', 'dao'],
            'tier3': ['app', 'web', 'game', 'data', 'code', 'smart', 'iot', 'ml', 'bot'],
        }
        
        self.lucky_numbers = ['8', '88', '888', '168', '520', '666', '777', '999', '123', '365', '100']
        
        self.vowels = set('aeiou')
        self.consonants = set('bcdfghjklmnpqrstvwxyz')
    
    def calculate_seo_score(self, domain_name: str) -> Tuple[float, Dict]:
        """計算 SEO 分數"""
        details = {}
        score = 0
        
        length = len(domain_name)
        if length <= 6:
            score += 30
            details['length_bonus'] = 30
        elif length <= 10:
            score += 20
            details['length_bonus'] = 20
        elif length <= 15:
            score += 10
            details['length_bonus'] = 10
        else:
            details['length_bonus'] = 0
        
        if domain_name.isalpha():
            score += 15
            details['pure_alpha'] = 15
        elif domain_name.isdigit():
            score += 10
            details['pure_numeric'] = 10
        else:
            details['mixed'] = 0
        
        for keyword, kw_list in self.premium_keywords.items():
            for kw in kw_list:
                if kw in domain_name.lower():
                    if keyword == 'tier1':
                        score += 25
                        details[f'keyword_{kw}'] = 25
                    elif keyword == 'tier2':
                        score += 15
                        details[f'keyword_{kw}'] = 15
                    elif keyword == 'tier3':
                        score += 10
                        details[f'keyword_{kw}'] = 10
                    break
        
        return min(score, 100), details
    
    def calculate_brand_value(self, domain_name: str) -> Tuple[float, Dict]:
        """計算品牌價值分數"""
        details = {}
        score = 0
        
        vowel_count = sum(1 for c in domain_name.lower() if c in self.vowels)
        consonant_count = sum(1 for c in domain_name.lower() if c in self.consonants)
        
        if 0.3 <= vowel_count / len(domain_name) <= 0.5:
            score += 20
            details['vowel_balance'] = 20
        else:
            details['vowel_balance'] = 0
        
        if not any(c * 3 in domain_name for c in set(domain_name)):
            score += 15
            details['no_triple_chars'] = 15
        else:
            details['no_triple_chars'] = 0
        
        if domain_name[0].isalpha():
            score += 10
            details['alpha_start'] = 10
        
        if not any(domain_name.startswith(x) or domain_name.endswith(x) 
                  for x in ['xx', 'qq', 'zz']):
            score += 10
            details['good_start_end'] = 10
        
        has_lucky = any(num in domain_name for num in self.lucky_numbers)
        if has_lucky:
            score += 15
            details['lucky_number'] = 15
        
        syllable_count = self._count_syllables(domain_name)
        if 2 <= syllable_count <= 4:
            score += 15
            details['syllable_bonus'] = 15
        elif syllable_count <= 6:
            score += 10
            details['syllable_bonus'] = 10
        else:
            details['syllable_bonus'] = 0
        
        return min(score, 100), details
    
    def calculate_market_trend_score(self, domain_name: str, tld: str) -> Tuple[float, Dict]:
        """計算市場趨勢分數"""
        details = {}
        score = 0
        
        if tld == '.com':
            score += 30
            details['tld_premium'] = 30
        elif tld == '.ai':
            score += 28
            details['tld_premium'] = 28
        elif tld == '.io':
            score += 25
            details['tld_premium'] = 25
        elif tld in ['.co', '.net']:
            score += 15
            details['tld_premium'] = 15
        else:
            score += 5
            details['tld_premium'] = 5
        
        trending_terms = ['ai', 'web3', 'nft', 'defi', 'dao', 'meta', 'crypto', 'saas', 'cloud', 'bot']
        for term in trending_terms:
            if term in domain_name.lower():
                score += 20
                details[f'trending_{term}'] = 20
                break
        
        if len(domain_name) <= 5:
            score += 25
            details['scarcity'] = 25
        elif len(domain_name) <= 8:
            score += 15
            details['scarcity'] = 15
        else:
            details['scarcity'] = 5
            score += 5
        
        if domain_name.isalpha() and len(domain_name) <= 6:
            score += 15
            details['premium_short'] = 15
        
        return min(score, 100), details
    
    def _count_syllables(self, text: str) -> int:
        """簡單的音節計數"""
        count = 0
        prev_was_vowel = False
        
        for char in text.lower():
            is_vowel = char in self.vowels
            if is_vowel and not prev_was_vowel:
                count += 1
            prev_was_vowel = is_vowel
        
        return max(1, count)
    
    def calculate_comprehensive_score(self, domain: str) -> Dict:
        """計算綜合評分"""
        parts = domain.rsplit('.', 1)
        if len(parts) == 2:
            domain_name, tld = parts
            tld = '.' + tld
        else:
            domain_name = parts[0]
            tld = '.com'
        
        seo_score, seo_details = self.calculate_seo_score(domain_name)
        brand_score, brand_details = self.calculate_brand_value(domain_name)
        market_score, market_details = self.calculate_market_trend_score(domain_name, tld)
        
        weights = {
            'seo': 0.35,
            'brand': 0.30,
            'market': 0.35
        }
        
        total_score = (seo_score * weights['seo'] + 
                      brand_score * weights['brand'] + 
                      market_score * weights['market'])
        
        return {
            'total_score': round(total_score, 2),
            'seo_score': round(seo_score, 2),
            'brand_score': round(brand_score, 2),
            'market_score': round(market_score, 2),
            'seo_details': seo_details,
            'brand_details': brand_details,
            'market_details': market_details,
            'rating': self._get_rating(total_score)
        }
    
    def _get_rating(self, score: float) -> str:
        """獲取評級"""
        if score >= 90:
            return '🏆 極品'
        elif score >= 80:
            return '⭐ 優秀'
        elif score >= 70:
            return '👍 良好'
        elif score >= 60:
            return '✓ 合格'
        else:
            return '- 一般'


class PerformanceMonitor:
    """性能監控器"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.start_memory = self.process.memory_info().rss / 1024 / 1024
        self.peak_memory = self.start_memory
        self.start_cpu = self.process.cpu_percent()
        self.checkpoints: List[Dict] = []
    
    def update(self) -> Dict:
        """更新監控數據"""
        current_memory = self.process.memory_info().rss / 1024 / 1024
        cpu_percent = self.process.cpu_percent()
        
        if current_memory > self.peak_memory:
            self.peak_memory = current_memory
        
        return {
            'memory_mb': current_memory,
            'peak_memory_mb': self.peak_memory,
            'memory_increase_mb': current_memory - self.start_memory,
            'cpu_percent': cpu_percent,
            'thread_count': threading.active_count()
        }
    
    def checkpoint(self, label: str):
        """記錄檢查點"""
        stats = self.update()
        stats['label'] = label
        stats['timestamp'] = time.time()
        self.checkpoints.append(stats)
    
    def get_report(self) -> str:
        """生成性能報告"""
        current = self.update()
        report = [
            "\n" + "="*80,
            "性能監控報告",
            "="*80,
            f"當前內存: {current['memory_mb']:.1f} MB",
            f"峰值內存: {current['peak_memory_mb']:.1f} MB",
            f"內存增長: {current['memory_increase_mb']:.1f} MB",
            f"CPU 使用: {current['cpu_percent']:.1f}%",
            f"活躍線程: {current['thread_count']}",
            "="*80
        ]
        return "\n".join(report)


class DomainGenerator:
    """域名生成器 - 改進的域名生成策略"""
    
    def __init__(self):
        self.tier1_keywords = ['ai', 'pay', 'bank', 'shop', 'nft', 'crypto', 'defi', 'web3']
        self.tier2_keywords = ['tech', 'cloud', 'finance', 'trade', 'saas', 'api', 'meta', 'dao']
        self.tier3_keywords = ['app', 'web', 'game', 'data', 'code', 'smart', 'iot', 'ml', 'bot']
        self.tier4_keywords = ['dev', 'net', 'media', 'video', 'social', 'live', 'eco', 'bio', 'lab']
        
        self.high_value_numbers = ['1', '8', '88', '888', '168', '520', '666', '777', '999', '123', '365', '100']
        self.letters = 'abcdefghijklmnopqrstuvwxyz'
        self.tlds = ['.com', '.io', '.co', '.net', '.org', '.ai']
        
        self.premium_tlds = ['.com', '.io', '.ai']
    
    def generate_keyword_domains(self) -> List[str]:
        """生成關鍵字域名"""
        domains = []
        all_keywords = (self.tier1_keywords + self.tier2_keywords + 
                       self.tier3_keywords + self.tier4_keywords)
        
        for keyword in all_keywords:
            for tld in self.tlds:
                domains.append(f"{keyword}{tld}")
        
        return domains
    
    def generate_keyword_number_domains(self) -> List[str]:
        """生成關鍵字+數字域名"""
        domains = []
        all_keywords = (self.tier1_keywords + self.tier2_keywords + 
                       self.tier3_keywords + self.tier4_keywords)
        
        for keyword in all_keywords:
            for num in self.high_value_numbers:
                for tld in self.tlds:
                    domains.append(f"{keyword}{num}{tld}")
        
        return domains
    
    def generate_combined_keywords(self) -> List[str]:
        """生成組合關鍵字域名"""
        domains = []
        keywords = self.tier1_keywords + self.tier2_keywords
        
        for i, kw1 in enumerate(keywords):
            for kw2 in keywords[i+1:]:
                combined = f"{kw1}{kw2}"
                if 4 <= len(combined) <= 10:
                    for tld in self.premium_tlds:
                        domains.append(f"{combined}{tld}")
        
        return domains
    
    def generate_pure_number_domains(self) -> List[str]:
        """生成純數字域名"""
        domains = []
        
        for num in self.high_value_numbers:
            for tld in self.tlds:
                domains.append(f"{num}{tld}")
        
        for i in range(100, 1000, 111):
            for tld in self.premium_tlds:
                domains.append(f"{i}{tld}")
        
        return domains
    
    def generate_short_letter_domains(self, max_length: int = 3) -> List[str]:
        """生成短字母域名 (2-3字母)"""
        domains = []
        
        for length in range(2, max_length + 1):
            if length == 2:
                for i in range(26):
                    for j in range(26):
                        domain_name = f"{self.letters[i]}{self.letters[j]}"
                        for tld in self.premium_tlds:
                            domains.append(f"{domain_name}{tld}")
            elif length == 3:
                for i in range(26):
                    for j in range(26):
                        for k in range(26):
                            domain_name = f"{self.letters[i]}{self.letters[j]}{self.letters[k]}"
                            for tld in self.premium_tlds:
                                domains.append(f"{domain_name}{tld}")
        
        return domains
    
    def generate_all(self, include_short_domains: bool = True) -> List[str]:
        """生成所有域名"""
        domains = []
        
        print("生成域名候選列表...")
        domains.extend(self.generate_keyword_domains())
        print(f"  ✓ 關鍵字域名: {len(domains)}")
        
        keyword_nums = self.generate_keyword_number_domains()
        domains.extend(keyword_nums)
        print(f"  ✓ 關鍵字+數字域名: {len(keyword_nums)}")
        
        combined = self.generate_combined_keywords()
        domains.extend(combined)
        print(f"  ✓ 組合關鍵字域名: {len(combined)}")
        
        pure_nums = self.generate_pure_number_domains()
        domains.extend(pure_nums)
        print(f"  ✓ 純數字域名: {len(pure_nums)}")
        
        if include_short_domains:
            short_domains = self.generate_short_letter_domains(max_length=3)
            domains.extend(short_domains)
            print(f"  ✓ 短字母域名: {len(short_domains)}")
        
        unique_domains = list(set(domains))
        print(f"\n總候選域名: {len(unique_domains)}")
        return unique_domains


class MultiThreadDomainHunter:
    """多線程域名搜索器 - 增強版"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config = self.load_config(config_file or CONFIG_FILE)
        
        access_key_id = self.config.get('access_key_id', ACCESS_KEY_ID)
        access_key_secret = self.config.get('access_key_secret', ACCESS_KEY_SECRET)
        
        self.hunter = DomainHunter(access_key_id, access_key_secret)
        self.generator = DomainGenerator()
        self.advanced_scorer = AdvancedDomainScorer()
        
        enable_cache = self.config.get('enable_cache', True)
        cache_max_age = self.config.get('cache_max_age', 86400)
        self.cache = DomainCache(max_age=cache_max_age) if enable_cache else None
        
        self.monitor = PerformanceMonitor()
        
        self.checked_domains = self.load_checked_domains()
        self.premium_domains = self.load_premium_results()
        self.available_domains = self.load_available_domains()
        
        self.lock = threading.Lock()
        self.stats = SearchStats(total_checked=len(self.checked_domains))
        
        self.shutdown_event = threading.Event()
        signal.signal(signal.SIGINT, self.signal_handler)
        
        self.checkpoint_file = Path('search_checkpoint.json')
        self.auto_save_enabled = self.config.get('auto_save_enabled', True)
        
        self.setup_logging()
    
    def load_config(self, config_file: str) -> Dict:
        """加載配置文件"""
        if Path(config_file).exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 加載配置文件失敗: {e}，使用默認配置")
        
        default_config = {
            'access_key_id': ACCESS_KEY_ID,
            'access_key_secret': ACCESS_KEY_SECRET,
            'max_workers': MAX_WORKERS,
            'base_delay': BASE_DELAY,
            'max_retries': MAX_RETRIES,
            'save_interval': SAVE_INTERVAL,
            'premium_price_threshold': 100,
            'premium_score_threshold': 70,
            'include_short_domains': False,
            'enable_cache': True,
            'cache_max_age': 86400,
            'auto_save_enabled': True,
            'checkpoint_interval': 100
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 已創建默認配置文件: {config_file}")
        return default_config
    
    def setup_logging(self):
        """設置日誌"""
        log_file = f'multi_search_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(threadName)-10s] %(levelname)-8s %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"日誌已初始化: {log_file}")
    
    def signal_handler(self, signum, frame):
        """處理中斷信號"""
        print("\n\n⚠️ 收到中斷信號，正在保存數據...")
        self.shutdown_event.set()
    
    def load_checked_domains(self) -> Set[str]:
        """加載已檢查的域名"""
        file_path = Path(CHECKED_DOMAINS_FILE)
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data) if isinstance(data, list) else set()
            except Exception as e:
                self.logger.error(f"加載已檢查域名文件失敗: {e}")
        return set()
    
    def save_checked_domains(self):
        """保存已檢查的域名"""
        try:
            with self.lock:
                with open(CHECKED_DOMAINS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(list(self.checked_domains), f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存已檢查域名失敗: {e}")
    
    def load_premium_results(self) -> List[Dict]:
        """加載精品域名結果"""
        file_path = Path(PREMIUM_RESULTS_FILE)
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"加載精品域名文件失敗: {e}")
        return []
    
    def save_premium_results(self):
        """保存精品域名結果"""
        try:
            with self.lock:
                with open(PREMIUM_RESULTS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.premium_domains, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存精品域名失敗: {e}")
    
    def load_available_domains(self) -> List[Dict]:
        """加載可購買域名"""
        file_path = Path(AVAILABLE_DOMAINS_FILE)
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"加載可購買域名文件失敗: {e}")
        return []
    
    def save_available_domains(self):
        """保存可購買域名"""
        try:
            with self.lock:
                with open(AVAILABLE_DOMAINS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.available_domains, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存可購買域名失敗: {e}")
    
    def save_checkpoint(self, current_index: int, total: int):
        """保存檢查點以支援斷點續傳"""
        if not self.auto_save_enabled:
            return
        
        try:
            checkpoint_data = {
                'timestamp': datetime.now().isoformat(),
                'current_index': current_index,
                'total_domains': total,
                'progress_percentage': (current_index / total * 100) if total > 0 else 0,
                'stats': self.stats.to_dict(),
                'checked_domains_count': len(self.checked_domains),
                'premium_domains_count': len(self.premium_domains),
                'available_domains_count': len(self.available_domains)
            }
            
            with self.lock:
                with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                    json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存檢查點失敗: {e}")
    
    def load_checkpoint(self) -> Optional[Dict]:
        """加載檢查點"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"加載檢查點失敗: {e}")
        return None
    
    def clear_checkpoint(self):
        """清除檢查點"""
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
                self.logger.info("✓ 已清除檢查點文件")
            except Exception as e:
                self.logger.error(f"清除檢查點失敗: {e}")
    
    def check_single_domain(self, domain: str) -> Optional[DomainResult]:
        """檢查單個域名（增強版 - 支援緩存）"""
        if domain in self.checked_domains:
            return None
        
        if self.shutdown_event.is_set():
            return None
        
        if self.cache:
            cached_result = self.cache.get(domain)
            if cached_result:
                with self.lock:
                    self.stats.cache_hits += 1
                    self.checked_domains.add(domain)
                    self.stats.total_checked = len(self.checked_domains)
                self.logger.debug(f"緩存命中: {domain}")
                return cached_result
        
        max_retries = self.config.get('max_retries', MAX_RETRIES)
        base_delay = self.config.get('base_delay', BASE_DELAY)
        retry_count = 0
        
        while retry_count < max_retries:
            if self.shutdown_event.is_set():
                return None
            
            try:
                request_start = time.time()
                time.sleep(base_delay)
                
                is_available, price = self.hunter.check_domain_availability(domain)
                request_time = time.time() - request_start
                
                with self.lock:
                    self.stats.record_response_time(request_time)
                    perf = self.monitor.update()
                    self.stats.peak_memory_mb = perf['peak_memory_mb']
                
                with self.lock:
                    self.checked_domains.add(domain)
                    self.stats.total_checked = len(self.checked_domains)
                
                result = DomainResult(
                    domain=domain,
                    available=is_available,
                    price=price,
                    check_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                
                if is_available and price is not None and price > 0:
                    basic_scores = self.hunter.calculate_total_score(domain)
                    advanced_scores = self.advanced_scorer.calculate_comprehensive_score(domain)
                    
                    combined_scores = {
                        'basic': basic_scores,
                        'advanced': advanced_scores,
                        'total_score': (basic_scores['total_score'] * 0.4 + 
                                      advanced_scores['total_score'] * 0.6)
                    }
                    result.scores = combined_scores
                    
                    with self.lock:
                        self.stats.available += 1
                        self.available_domains.append(asdict(result))
                    
                    print(f"✓ 可購買 | {domain:25s} | ¥{price:8.2f} | 評分: {combined_scores['total_score']:5.1f} "
                          f"(SEO:{advanced_scores['seo_score']:.0f} 品牌:{advanced_scores['brand_score']:.0f} "
                          f"市場:{advanced_scores['market_score']:.0f}) {advanced_scores['rating']}")
                    
                    premium_threshold_price = self.config.get('premium_price_threshold', 100)
                    premium_threshold_score = self.config.get('premium_score_threshold', 70)
                    
                    if price < premium_threshold_price and combined_scores['total_score'] >= premium_threshold_score:
                        profit_estimate = self.hunter.estimate_resale_profit(
                            domain, price, combined_scores['total_score']
                        )
                        result.profit_estimate = profit_estimate
                        
                        premium_info = {
                            'domain': domain,
                            'purchase_price': price,
                            'scores': scores,
                            'profit_estimate': profit_estimate,
                            'scan_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        with self.lock:
                            self.premium_domains.append(premium_info)
                            self.stats.premium = len(self.premium_domains)
                        
                        print(f"   🌟 精品域名！利潤: ¥{profit_estimate['estimated_profit']:.2f} "
                              f"ROI: {profit_estimate['roi_percentage']:.0f}%")
                
                if self.cache:
                    self.cache.set(domain, result)
                
                elif is_available and (price is None or price == 0):
                    with self.lock:
                        self.stats.no_price += 1
                else:
                    with self.lock:
                        self.stats.registered += 1
                
                return result
            
            except Exception as e:
                error_msg = str(e)
                
                if any(keyword in error_msg for keyword in 
                      ['Throttling', 'flow control', 'Request was denied', 'rate limit']):
                    retry_count += 1
                    with self.lock:
                        self.stats.throttled += 1
                    
                    wait_time = min(2 ** retry_count * 2, 60)
                    self.logger.warning(
                        f"⚠️ API限流 {domain}，等待 {wait_time}秒後重試 ({retry_count}/{max_retries})"
                    )
                    
                    if not self.shutdown_event.wait(wait_time):
                        continue
                    return None
                else:
                    with self.lock:
                        self.stats.errors += 1
                    self.logger.error(f"❌ 檢查域名 {domain} 時出錯: {error_msg}")
                    with self.lock:
                        self.checked_domains.add(domain)
                    return None
        
        with self.lock:
            self.stats.errors += 1
        self.logger.error(f"❌ 域名 {domain} 重試 {max_retries} 次後仍失敗，跳過")
        with self.lock:
            self.checked_domains.add(domain)
        return None
    
    def run_search(self, max_workers: Optional[int] = None):
        """運行域名搜索（增強版 - 支援斷點續傳和性能監控）"""
        if max_workers is None:
            max_workers = self.config.get('max_workers', MAX_WORKERS)
        
        checkpoint = self.load_checkpoint()
        if checkpoint:
            print(f"\n✓ 發現檢查點: {checkpoint['timestamp']}")
            print(f"  進度: {checkpoint['progress_percentage']:.1f}% "
                  f"({checkpoint['current_index']}/{checkpoint['total_domains']})")
            print(f"  已發現精品: {checkpoint['premium_domains_count']}")
        
        self.monitor.checkpoint("開始生成域名")
        include_short = self.config.get('include_short_domains', False)
        all_domains = self.generator.generate_all(include_short_domains=include_short)
        remaining_domains = [d for d in all_domains if d not in self.checked_domains]
        self.monitor.checkpoint("域名生成完成")
        
        print("\n" + "="*80)
        print("多線程域名搜索系統 (增強版)")
        print("="*80)
        print(f"線程數: {max_workers}")
        print(f"總候選域名: {len(all_domains):,}")
        print(f"已檢查: {len(self.checked_domains):,}")
        print(f"待檢查: {len(remaining_domains):,}")
        print(f"已發現精品: {len(self.premium_domains)}")
        print(f"保存間隔: 每 {self.config.get('save_interval', SAVE_INTERVAL)} 個域名")
        print(f"緩存: {'啟用' if self.cache else '禁用'}")
        print(f"斷點續傳: {'啟用' if self.auto_save_enabled else '禁用'}")
        print("="*80)
        
        if len(remaining_domains) == 0:
            print("\n✅ 所有域名已檢查完畢！")
            self.print_final_report(0)
            return
        
        print(f"\n開始掃描 {len(remaining_domains):,} 個域名...\n")
        
        self.stats.start_time = time.time()
        start_time = self.stats.start_time
        save_counter = 0
        save_interval = self.config.get('save_interval', SAVE_INTERVAL)
        checkpoint_interval = self.config.get('checkpoint_interval', 100)
        
        self.monitor.checkpoint("開始搜索")
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self.check_single_domain, domain): domain 
                          for domain in remaining_domains}
                
                for completed, future in enumerate(as_completed(futures), 1):
                    if self.shutdown_event.is_set():
                        print("\n⚠️ 正在取消剩餘任務...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    
                    try:
                        result = future.result()
                        save_counter += 1
                        
                        if save_counter % save_interval == 0:
                            self.save_all()
                            
                            if self.auto_save_enabled and save_counter % checkpoint_interval == 0:
                                self.save_checkpoint(completed, len(remaining_domains))
                            
                            if self.cache and save_counter % (save_interval * 2) == 0:
                                self.cache.save_cache()
                            
                            elapsed = time.time() - start_time
                            rate = completed / elapsed if elapsed > 0 else 0
                            remaining = len(remaining_domains) - completed
                            eta = remaining / rate if rate > 0 else 0
                            
                            perf = self.monitor.update()
                            
                            print(f"\n--- 進度: {completed:,}/{len(remaining_domains):,} ({completed/len(remaining_domains)*100:.1f}%) | "
                                  f"速度: {rate:.2f}域名/秒 | "
                                  f"精品: {self.stats.premium} | "
                                  f"限流: {self.stats.throttled} | "
                                  f"緩存命中: {self.stats.cache_hits} | "
                                  f"內存: {perf['memory_mb']:.0f}MB | "
                                  f"ETA: {eta/60:.1f}分鐘 ---\n")
                    
                    except Exception as e:
                        self.logger.error(f"處理結果時出錯: {str(e)}")
        
        except KeyboardInterrupt:
            print("\n\n⚠️ 用戶中斷掃描")
            self.shutdown_event.set()
        
        except Exception as e:
            self.logger.error(f"搜索過程出錯: {str(e)}")
        
        finally:
            self.save_all()
            if self.cache:
                self.cache.save_cache()
            if self.auto_save_enabled:
                self.clear_checkpoint()
            
            self.monitor.checkpoint("搜索完成")
            elapsed = time.time() - start_time
            self.print_final_report(elapsed)
    
    def save_all(self):
        """保存所有數據"""
        self.save_checked_domains()
        self.save_premium_results()
        self.save_available_domains()
    
    def generate_analytics_report(self) -> Dict:
        """生成數據分析報告"""
        analytics = {
            'summary': {
                'total_checked': len(self.checked_domains),
                'available_count': len(self.available_domains),
                'premium_count': len(self.premium_domains),
                'availability_rate': (len(self.available_domains) / len(self.checked_domains) * 100) 
                                     if len(self.checked_domains) > 0 else 0
            },
            'price_distribution': {},
            'score_distribution': {},
            'tld_statistics': {},
            'top_domains': []
        }
        
        if self.available_domains:
            prices = [d['price'] for d in self.available_domains if d.get('price')]
            if prices:
                analytics['price_distribution'] = {
                    'min': min(prices),
                    'max': max(prices),
                    'avg': sum(prices) / len(prices),
                    'median': sorted(prices)[len(prices) // 2]
                }
            
            tld_counter = defaultdict(int)
            for domain_info in self.available_domains:
                domain = domain_info['domain']
                tld = '.' + domain.rsplit('.', 1)[1] if '.' in domain else '.unknown'
                tld_counter[tld] += 1
            
            analytics['tld_statistics'] = dict(tld_counter)
        
        if self.premium_domains:
            scores = []
            for d in self.premium_domains:
                if 'scores' in d and 'total_score' in d['scores']:
                    scores.append(d['scores']['total_score'])
            
            if scores:
                analytics['score_distribution'] = {
                    'min': min(scores),
                    'max': max(scores),
                    'avg': sum(scores) / len(scores)
                }
            
            sorted_premiums = sorted(
                self.premium_domains,
                key=lambda x: x['profit_estimate']['roi_percentage'] 
                if 'profit_estimate' in x else 0,
                reverse=True
            )
            analytics['top_domains'] = sorted_premiums[:10]
        
        return analytics
    
    def save_analytics_report(self):
        """保存分析報告"""
        try:
            analytics = self.generate_analytics_report()
            report_file = f'analytics_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(analytics, f, ensure_ascii=False, indent=2)
            
            print(f"\n✓ 分析報告已保存: {report_file}")
            return report_file
        except Exception as e:
            self.logger.error(f"保存分析報告失敗: {e}")
            return None
    
    def print_final_report(self, elapsed: float):
        """打印最終報告（增強版 - 包含性能監控）"""
        self.stats.print_summary(elapsed)
        
        if self.monitor:
            print(self.monitor.get_report())
        
        if self.premium_domains:
            print("\n" + "="*80)
            print(f"發現 {len(self.premium_domains)} 個精品域名")
            print("="*80)
            
            self.premium_domains.sort(key=lambda x: x['scores']['total_score'], reverse=True)
            
            top_n = min(20, len(self.premium_domains))
            for idx, domain_info in enumerate(self.premium_domains[:top_n], 1):
                domain = domain_info['domain']
                score = domain_info['scores']['total_score']
                price = domain_info['purchase_price']
                profit = domain_info['profit_estimate']['estimated_profit']
                roi = domain_info['profit_estimate']['roi_percentage']
                
                print(f"#{idx:02d} {domain:25s} | 評分: {score:5.1f} | "
                      f"價格: ¥{price:6.2f} | 利潤: ¥{profit:8.2f} | ROI: {roi:5.0f}%")
            
            if len(self.premium_domains) > top_n:
                print(f"\n... 還有 {len(self.premium_domains)-top_n} 個，查看 {PREMIUM_RESULTS_FILE}")
            
            try:
                self.hunter.generate_report(self.premium_domains)
                print("\n✓ HTML 報告已生成")
            except Exception as e:
                self.logger.error(f"生成報告失敗: {e}")
        
        print("\n檔案已保存:")
        print(f"  ✓ {CHECKED_DOMAINS_FILE} - 已檢查域名列表 ({len(self.checked_domains):,} 個)")
        print(f"  ✓ {AVAILABLE_DOMAINS_FILE} - 可購買域名列表 ({len(self.available_domains)} 個)")
        print(f"  ✓ {PREMIUM_RESULTS_FILE} - 精品域名列表 ({len(self.premium_domains)} 個)")
        
        analytics_file = self.save_analytics_report()
        if analytics_file:
            print(f"  ✓ {analytics_file} - 數據分析報告")
        
        print("="*80)


def main():
    """主函數"""
    print("域名搜索系統啟動中...")
    
    try:
        hunter = MultiThreadDomainHunter()
        hunter.run_search()
    except Exception as e:
        print(f"\n❌ 程序異常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
