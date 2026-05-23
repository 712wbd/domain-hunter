import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Set
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

from domain_hunter import DomainHunter

ACCESS_KEY_ID = 'your_access_key_id'
ACCESS_KEY_SECRET = 'your_access_key_secret'

CHECKED_DOMAINS_FILE = 'checked_domains.json'
PREMIUM_RESULTS_FILE = 'premium_results.json'
AVAILABLE_DOMAINS_FILE = 'available_domains.json'

MAX_WORKERS = 5

class MultiThreadDomainHunter:
    def __init__(self):
        self.hunter = DomainHunter(ACCESS_KEY_ID, ACCESS_KEY_SECRET)
        self.checked_domains = self.load_checked_domains()
        self.premium_domains = self.load_premium_results()
        self.available_domains = self.load_available_domains()
        self.lock = threading.Lock()
        
        self.stats = {
            'total_checked': len(self.checked_domains),
            'available': 0,
            'premium': len(self.premium_domains),
            'registered': 0,
            'no_price': 0
        }
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(threadName)s] %(message)s',
            handlers=[
                logging.FileHandler(f'multi_search_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_checked_domains(self) -> Set[str]:
        if os.path.exists(CHECKED_DOMAINS_FILE):
            with open(CHECKED_DOMAINS_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        return set()
    
    def save_checked_domains(self):
        with self.lock:
            with open(CHECKED_DOMAINS_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(self.checked_domains), f, ensure_ascii=False, indent=2)
    
    def load_premium_results(self) -> List[Dict]:
        if os.path.exists(PREMIUM_RESULTS_FILE):
            with open(PREMIUM_RESULTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_premium_results(self):
        with self.lock:
            with open(PREMIUM_RESULTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.premium_domains, f, ensure_ascii=False, indent=2)
    
    def load_available_domains(self) -> List[Dict]:
        if os.path.exists(AVAILABLE_DOMAINS_FILE):
            with open(AVAILABLE_DOMAINS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_available_domains(self):
        with self.lock:
            with open(AVAILABLE_DOMAINS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.available_domains, f, ensure_ascii=False, indent=2)
    
    def generate_domains(self) -> List[str]:
        domains = []
        
        tier1_keywords = ['ai', 'pay', 'bank', 'shop', 'nft', 'crypto', 'defi']
        tier2_keywords = ['tech', 'cloud', 'finance', 'trade', 'saas', 'api', 'meta', 'web3']
        tier3_keywords = ['app', 'web', 'game', 'data', 'code', 'smart', 'iot', 'ml', 'dao']
        tier4_keywords = ['dev', 'net', 'media', 'video', 'social', 'live', 'eco', 'bio']
        
        all_keywords = tier1_keywords + tier2_keywords + tier3_keywords + tier4_keywords
        
        high_value_numbers = ['1', '8', '88', '888', '168', '520', '666', '777', '999', '123']
        letters = 'abcdefghijklmnopqrstuvwxyz'
        tlds = ['.com', '.io', '.co', '.net', '.org']
        
        for keyword in all_keywords:
            for tld in tlds:
                domains.append(f"{keyword}{tld}")
        
        for keyword in all_keywords:
            for num in high_value_numbers:
                for tld in tlds:
                    domains.append(f"{keyword}{num}{tld}")
        
        for keyword in all_keywords[:20]:
            for keyword2 in all_keywords[:20]:
                if keyword != keyword2:
                    combined = f"{keyword}{keyword2}"
                    if len(combined) <= 8:
                        for tld in ['.com', '.io']:
                            domains.append(f"{combined}{tld}")
        
        for num in high_value_numbers:
            for tld in tlds:
                domains.append(f"{num}{tld}")
        
        for i in range(len(letters)):
            for j in range(len(letters)):
                domain_name = f"{letters[i]}{letters[j]}"
                for tld in ['.com', '.io']:
                    domains.append(f"{domain_name}{tld}")
        
        for i in range(len(letters)):
            for j in range(len(letters)):
                for k in range(len(letters)):
                    domain_name = f"{letters[i]}{letters[j]}{letters[k]}"
                    for tld in ['.com', '.io']:
                        domains.append(f"{domain_name}{tld}")
        
        return list(set(domains))
    
    def check_single_domain(self, domain: str, max_retries=5) -> Dict:
        if domain in self.checked_domains:
            return None
        
        retry_count = 0
        base_delay = 0.8
        
        while retry_count < max_retries:
            try:
                time.sleep(base_delay)
                
                is_available, price = self.hunter.check_domain_availability(domain)
                
                with self.lock:
                    self.checked_domains.add(domain)
                    self.stats['total_checked'] = len(self.checked_domains)
                
                result = {
                    'domain': domain,
                    'available': is_available,
                    'price': price,
                    'check_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                if is_available and price is not None and price > 0:
                    scores = self.hunter.calculate_total_score(domain)
                    result['scores'] = scores
                    
                    with self.lock:
                        self.stats['available'] += 1
                        self.available_domains.append(result)
                        self.save_available_domains()
                    
                    print(f"✓ 可購買 | {domain:20s} | ¥{price:6.2f} | 評分: {scores['total_score']:.1f}")
                    
                    if price < 100 and scores['total_score'] >= 70:
                        profit_estimate = self.hunter.estimate_resale_profit(domain, price, scores['total_score'])
                        
                        premium_info = {
                            'domain': domain,
                            'purchase_price': price,
                            'scores': scores,
                            'profit_estimate': profit_estimate,
                            'scan_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        with self.lock:
                            self.premium_domains.append(premium_info)
                            self.stats['premium'] = len(self.premium_domains)
                            self.save_premium_results()
                        
                        print(f"   🌟 精品域名！利潤: ¥{profit_estimate['estimated_profit']:.2f} ROI: {profit_estimate['roi_percentage']:.0f}%")
                
                elif is_available and (price is None or price == 0):
                    with self.lock:
                        self.stats['no_price'] += 1
                else:
                    with self.lock:
                        self.stats['registered'] += 1
                
                return result
                
            except Exception as e:
                error_msg = str(e)
                
                if 'Throttling' in error_msg or 'flow control' in error_msg or 'Request was denied' in error_msg:
                    retry_count += 1
                    wait_time = min(2 ** retry_count * 2, 60)
                    self.logger.warning(f"⚠️ API限流 {domain}，等待 {wait_time}秒後重試 ({retry_count}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f"❌ 檢查域名 {domain} 時出錯: {error_msg}")
                    with self.lock:
                        self.checked_domains.add(domain)
                    return None
        
        self.logger.error(f"❌ 域名 {domain} 重試 {max_retries} 次後仍失敗，跳過")
        with self.lock:
            self.checked_domains.add(domain)
        return None
    
    def run_search(self, max_workers=MAX_WORKERS):
        all_domains = self.generate_domains()
        remaining_domains = [d for d in all_domains if d not in self.checked_domains]
        
        print("="*80)
        print("多線程域名搜索系統")
        print("="*80)
        print(f"線程數: {max_workers}")
        print(f"總候選域名: {len(all_domains)}")
        print(f"已檢查: {len(self.checked_domains)}")
        print(f"待檢查: {len(remaining_domains)}")
        print(f"已發現精品: {len(self.premium_domains)}")
        print("="*80)
        
        if len(remaining_domains) == 0:
            print("\n✅ 所有域名已檢查完畢！")
            return
        
        print(f"\n開始掃描 {len(remaining_domains)} 個域名...\n")
        
        start_time = time.time()
        save_counter = 0
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self.check_single_domain, domain): domain 
                          for domain in remaining_domains}
                
                for completed, future in enumerate(as_completed(futures), 1):
                    try:
                        result = future.result()
                        save_counter += 1
                        
                        if save_counter % 50 == 0:
                            self.save_checked_domains()
                            elapsed = time.time() - start_time
                            rate = completed / elapsed if elapsed > 0 else 0
                            remaining = len(remaining_domains) - completed
                            eta = remaining / rate if rate > 0 else 0
                            
                            print(f"\n--- 進度: {completed}/{len(remaining_domains)} | "
                                  f"速度: {rate:.1f}域名/秒 | "
                                  f"精品: {self.stats['premium']} | "
                                  f"ETA: {eta/60:.1f}分鐘 ---\n")
                    
                    except Exception as e:
                        self.logger.error(f"處理結果時出錯: {str(e)}")
        
        except KeyboardInterrupt:
            print("\n\n⚠️ 用戶中斷掃描")
        
        finally:
            self.save_checked_domains()
            self.save_premium_results()
            self.save_available_domains()
            
            elapsed = time.time() - start_time
            
            print("\n" + "="*80)
            print("掃描完成")
            print("="*80)
            print(f"總檢查域名: {self.stats['total_checked']}")
            print(f"可購買域名: {self.stats['available']}")
            print(f"精品域名: {self.stats['premium']}")
            print(f"已註冊: {self.stats['registered']}")
            print(f"無價格: {self.stats['no_price']}")
            print(f"總耗時: {elapsed/60:.1f} 分鐘")
            print(f"平均速度: {self.stats['total_checked']/elapsed:.1f} 域名/秒")
            
            if self.premium_domains:
                print("\n" + "="*80)
                print(f"發現 {len(self.premium_domains)} 個精品域名")
                print("="*80)
                
                self.premium_domains.sort(key=lambda x: x['scores']['total_score'], reverse=True)
                
                for idx, domain_info in enumerate(self.premium_domains[:10], 1):
                    domain = domain_info['domain']
                    score = domain_info['scores']['total_score']
                    price = domain_info['purchase_price']
                    profit = domain_info['profit_estimate']['estimated_profit']
                    
                    print(f"#{idx:02d} {domain:20s} | 評分: {score:.1f} | 價格: ¥{price:.2f} | 利潤: ¥{profit:.2f}")
                
                if len(self.premium_domains) > 10:
                    print(f"\n... 還有 {len(self.premium_domains)-10} 個，查看 {PREMIUM_RESULTS_FILE}")
                
                self.hunter.generate_report(self.premium_domains)
            
            print("\n檔案已保存:")
            print(f"  ✓ {CHECKED_DOMAINS_FILE} - 已檢查域名列表")
            print(f"  ✓ {AVAILABLE_DOMAINS_FILE} - 可購買域名列表")
            print(f"  ✓ {PREMIUM_RESULTS_FILE} - 精品域名列表")
            print("="*80)


def main():
    hunter = MultiThreadDomainHunter()
    hunter.run_search(max_workers=5)


if __name__ == "__main__":
    main()
