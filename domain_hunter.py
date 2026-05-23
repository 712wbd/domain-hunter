import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import requests
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
import re


class DomainHunter:
    
    def __init__(self, access_key_id: str, access_key_secret: str, region: str = 'cn-hangzhou'):
        self.client = AcsClient(access_key_id, access_key_secret, region)
        self.setup_logging()
        self.load_config()
        
    def setup_logging(self):
        log_filename = f'domain_hunter_{datetime.now().strftime("%Y%m%d")}.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def load_config(self):
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.logger.warning("配置文件未找到，使用默認配置")
            self.config = self.get_default_config()
            
    def get_default_config(self) -> Dict:
        return {
            "max_price": 100,
            "max_length": 6,
            "min_score": 70,
            "industry_keywords": [
                "ai", "tech", "cloud", "data", "shop", "pay", "game", "net", 
                "app", "web", "dev", "code", "digital", "smart", "auto", "finance",
                "bank", "trade", "edu", "health", "media", "social"
            ],
            "high_value_numbers": ["888", "666", "999", "123", "520", "168"],
            "tld_list": [".com", ".cn", ".net", ".org", ".com.cn"],
            "renewal_costs": {
                ".com": 60,
                ".cn": 40,
                ".net": 70,
                ".org": 80,
                ".com.cn": 50
            },
            "api_delay": 0.5,
            "batch_size": 100
        }
    
    def check_domain_availability(self, domain: str) -> Tuple[bool, Optional[float]]:
        try:
            request = CommonRequest()
            request.set_accept_format('json')
            request.set_domain('domain.aliyuncs.com')
            request.set_method('POST')
            request.set_version('2018-01-29')
            request.set_action_name('CheckDomain')
            request.add_query_param('DomainName', domain)
            
            response = self.client.do_action_with_exception(request)
            result = json.loads(response)
            
            time.sleep(self.config['api_delay'])
            
            avail = result.get('Avail')
            if avail == 1 or avail == '1':
                price = result.get('Price')
                if price is None:
                    static_price_info = result.get('StaticPriceInfo', {})
                    price_list = static_price_info.get('PriceInfo', [])
                    if price_list and len(price_list) > 0:
                        price = price_list[0].get('money', 0)
                    else:
                        price = 0
                
                return True, float(price)
            return False, None
            
        except Exception as e:
            self.logger.error(f"查詢域名 {domain} 時發生錯誤: {str(e)}")
            return False, None
    
    def generate_domain_candidates(self) -> List[str]:
        candidates = []
        
        letters = 'abcdefghijklmnopqrstuvwxyz'
        
        for length in range(2, self.config['max_length'] + 1):
            if length == 2:
                for i in letters:
                    for j in letters:
                        for tld in self.config['tld_list']:
                            candidates.append(f"{i}{j}{tld}")
            
            for keyword in self.config['industry_keywords']:
                if len(keyword) <= self.config['max_length']:
                    for tld in self.config['tld_list']:
                        candidates.append(f"{keyword}{tld}")
        
        for num_pattern in self.config['high_value_numbers']:
            if len(num_pattern) <= self.config['max_length']:
                for tld in self.config['tld_list']:
                    candidates.append(f"{num_pattern}{tld}")
        
        for keyword in self.config['industry_keywords']:
            for num in ['1', '2', '8', '88', '168', '888']:
                domain_name = f"{keyword}{num}"
                if len(domain_name) <= self.config['max_length']:
                    for tld in self.config['tld_list']:
                        candidates.append(f"{domain_name}{tld}")
        
        return list(set(candidates))
    
    def calculate_length_score(self, domain_name: str) -> float:
        domain_without_tld = domain_name.split('.')[0]
        length = len(domain_without_tld)
        
        if length == 2:
            return 20.0
        elif length == 3:
            return 18.0
        elif length == 4:
            return 15.0
        elif length == 5:
            return 11.0
        elif length == 6:
            return 7.0
        elif length == 7:
            return 3.0
        else:
            return 0.0
    
    def calculate_renewal_cost_score(self, tld: str) -> float:
        renewal_cost = self.config['renewal_costs'].get(tld, 100)
        
        if renewal_cost < 50:
            return 15.0
        elif renewal_cost < 60:
            return 13.5
        elif renewal_cost < 70:
            return 12.0
        elif renewal_cost < 80:
            return 10.0
        elif renewal_cost < 90:
            return 7.5
        elif renewal_cost < 100:
            return 5.0
        else:
            return 0.0
    
    def calculate_industry_value_score(self, domain_name: str) -> float:
        domain_without_tld = domain_name.split('.')[0].lower()
        
        tier1_industries = ['ai', 'pay', 'bank', 'shop', 'nft', 'crypto', 'defi']
        tier2_industries = ['tech', 'cloud', 'finance', 'trade', 'saas', 'api', 'meta']
        tier3_industries = ['app', 'web', 'game', 'data', 'code', 'smart', 'iot', 'ml']
        tier4_industries = ['dev', 'net', 'media', 'video', 'social', 'live', 'eco']
        
        for keyword in tier1_industries:
            if keyword in domain_without_tld:
                return 25.0
        
        for keyword in tier2_industries:
            if keyword in domain_without_tld:
                return 20.0
        
        for keyword in tier3_industries:
            if keyword in domain_without_tld:
                return 15.0
        
        for keyword in tier4_industries:
            if keyword in domain_without_tld:
                return 10.0
        
        for keyword in self.config['industry_keywords']:
            if keyword in domain_without_tld:
                return 5.0
        
        return 0.0
    
    def calculate_brand_adaptability_score(self, domain_name: str) -> int:
        domain_without_tld = domain_name.split('.')[0].lower()
        score = 15
        
        if re.search(r'[0-9]+[a-z]+[0-9]+', domain_without_tld):
            score -= 5
        
        confusing_patterns = ['il', 'li', 'o0', '0o', 'vv', 'wv', 'rn', 'nm']
        for pattern in confusing_patterns:
            if pattern in domain_without_tld:
                score -= 3
                break
        
        if len(domain_without_tld) > 0 and domain_without_tld.isalnum():
            pass
        else:
            score -= 5
        
        vowels = set('aeiou')
        has_vowel = any(c in vowels for c in domain_without_tld if c.isalpha())
        if not has_vowel and domain_without_tld.isalpha():
            score -= 5
        
        return max(0, score)
    
    def calculate_tld_value_score(self, domain: str) -> float:
        if domain.endswith('.com'):
            return 15.0
        elif domain.endswith('.io'):
            return 13.0
        elif domain.endswith('.co'):
            return 12.0
        elif domain.endswith('.net'):
            return 10.0
        elif domain.endswith('.org'):
            return 8.0
        else:
            return 5.0
    
    def calculate_market_liquidity_score(self, domain_name: str) -> int:
        domain_without_tld = domain_name.split('.')[0].lower()
        score = 5
        
        if domain_without_tld.isdigit():
            if len(domain_without_tld) <= 4:
                score = 10
            else:
                score = 7
        
        for pattern in self.config['high_value_numbers']:
            if pattern in domain_without_tld:
                score = 10
                break
        
        if domain_without_tld.isalpha() and len(domain_without_tld) <= 4:
            score = 10
        
        for keyword in ['ai', 'pay', 'shop', 'bank', 'tech']:
            if keyword == domain_without_tld:
                score = 10
                break
        
        return score
    
    def calculate_total_score(self, domain: str) -> Dict[str, int]:
        tld = '.' + domain.split('.', 1)[1]
        
        scores = {
            'length_score': self.calculate_length_score(domain),
            'renewal_cost_score': self.calculate_renewal_cost_score(tld),
            'industry_value_score': self.calculate_industry_value_score(domain),
            'brand_adaptability_score': self.calculate_brand_adaptability_score(domain),
            'tld_value_score': self.calculate_tld_value_score(domain),
            'market_liquidity_score': self.calculate_market_liquidity_score(domain)
        }
        
        scores['total_score'] = sum(scores.values())
        
        return scores
    
    def estimate_resale_profit(self, domain: str, purchase_price: float, total_score: int) -> Dict[str, float]:
        base_multiplier = 1.5
        
        if total_score >= 90:
            multiplier = 10.0
        elif total_score >= 80:
            multiplier = 5.0
        elif total_score >= 70:
            multiplier = 3.0
        else:
            multiplier = base_multiplier
        
        domain_without_tld = domain.split('.')[0]
        if len(domain_without_tld) <= 3:
            multiplier *= 2
        
        estimated_resale_price = purchase_price * multiplier
        profit = estimated_resale_price - purchase_price
        roi = (profit / purchase_price) * 100 if purchase_price > 0 else 0
        
        return {
            'purchase_price': purchase_price,
            'estimated_resale_price': estimated_resale_price,
            'estimated_profit': profit,
            'roi_percentage': roi
        }
    
    def scan_domains(self, limit: Optional[int] = None) -> List[Dict]:
        self.logger.info("開始掃描域名...")
        candidates = self.generate_domain_candidates()
        
        if limit:
            candidates = candidates[:limit]
        
        self.logger.info(f"生成 {len(candidates)} 個候選域名")
        
        premium_domains = []
        scanned_count = 0
        available_count = 0
        
        for domain in candidates:
            scanned_count += 1
            
            if scanned_count % 50 == 0:
                self.logger.info(f"已掃描 {scanned_count}/{len(candidates)} 個域名")
            
            is_available, price = self.check_domain_availability(domain)
            
            if is_available and price is not None and price < self.config['max_price']:
                available_count += 1
                
                scores = self.calculate_total_score(domain)
                
                if scores['total_score'] >= self.config['min_score']:
                    profit_estimate = self.estimate_resale_profit(domain, price, scores['total_score'])
                    
                    domain_info = {
                        'domain': domain,
                        'purchase_price': price,
                        'scores': scores,
                        'profit_estimate': profit_estimate,
                        'scan_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    premium_domains.append(domain_info)
                    self.logger.info(f"發現精品域名: {domain} (評分: {scores['total_score']})")
        
        premium_domains.sort(key=lambda x: x['scores']['total_score'], reverse=True)
        
        self.logger.info(f"掃描完成: 共掃描 {scanned_count} 個域名，{available_count} 個可用，{len(premium_domains)} 個精品域名")
        
        return premium_domains
    
    def generate_report(self, premium_domains: List[Dict], output_file: str = None):
        if output_file is None:
            output_file = f'domain_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        
        report = {
            'scan_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'total_premium_domains': len(premium_domains),
            'min_score_threshold': self.config['min_score'],
            'domains': premium_domains
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"報告已生成: {output_file}")
        
        self.generate_readable_report(premium_domains)
    
    def generate_readable_report(self, premium_domains: List[Dict]):
        report_file = f'domain_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("精品域名搜索報告\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"掃描時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"發現精品域名總數: {len(premium_domains)}\n")
            f.write(f"評分閾值: {self.config['min_score']}分\n\n")
            
            if premium_domains:
                f.write("-" * 80 + "\n")
                f.write("精品域名清單 (按評分排序)\n")
                f.write("-" * 80 + "\n\n")
                
                for idx, domain_info in enumerate(premium_domains, 1):
                    domain = domain_info['domain']
                    scores = domain_info['scores']
                    profit = domain_info['profit_estimate']
                    
                    f.write(f"#{idx} {domain}\n")
                    f.write(f"  總評分: {scores['total_score']}/100\n")
                    f.write(f"  註冊價格: ¥{domain_info['purchase_price']:.2f}\n")
                    f.write(f"  預估轉售價: ¥{profit['estimated_resale_price']:.2f}\n")
                    f.write(f"  預估利潤: ¥{profit['estimated_profit']:.2f}\n")
                    f.write(f"  投資回報率: {profit['roi_percentage']:.1f}%\n")
                    f.write(f"\n  評分明細:\n")
                    f.write(f"    - 域名長度分: {scores['length_score']}/20\n")
                    f.write(f"    - 續費成本分: {scores['renewal_cost_score']}/15\n")
                    f.write(f"    - 行業價值分: {scores['industry_value_score']}/25\n")
                    f.write(f"    - 品牌適配性分: {scores['brand_adaptability_score']}/15\n")
                    f.write(f"    - 後綴價值分: {scores['tld_value_score']}/15\n")
                    f.write(f"    - 市場流通性分: {scores['market_liquidity_score']}/10\n")
                    f.write("\n")
            else:
                f.write("未發現符合條件的精品域名\n")
            
            f.write("=" * 80 + "\n")
        
        self.logger.info(f"可讀報告已生成: {report_file}")


def main():
    ACCESS_KEY_ID = 'YOUR_ACCESS_KEY_ID'
    ACCESS_KEY_SECRET = 'YOUR_ACCESS_KEY_SECRET'
    
    try:
        hunter = DomainHunter(ACCESS_KEY_ID, ACCESS_KEY_SECRET)
        
        premium_domains = hunter.scan_domains(limit=200)
        
        hunter.generate_report(premium_domains)
        
        print(f"\n掃描完成！發現 {len(premium_domains)} 個精品域名")
        print("詳細報告已保存至文件")
        
    except Exception as e:
        logging.error(f"程序執行出錯: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
