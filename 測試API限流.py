#!/usr/bin/env python3

import sys
import time
from multi_thread_search import MultiThreadDomainHunter

def test_throttling_fix():
    print("="*60)
    print("測試 API 限流修復")
    print("="*60)
    print("\n本測試將掃描20個域名來驗證限流處理機制\n")
    
    hunter = MultiThreadDomainHunter()
    
    test_domains = [
        'ai1.com', 'ai2.com', 'ai3.com', 'ai8.com', 
        'pay1.io', 'pay2.io', 'pay8.io',
        'nft1.com', 'nft2.com', 'nft8.com',
        'defi1.io', 'defi2.io', 'defi8.io',
        'dao1.com', 'dao2.com', 'dao8.com',
        'web31.io', 'web32.io', 'web38.io',
        'crypto1.co', 'crypto8.co'
    ]
    
    print(f"測試域名數量: {len(test_domains)}")
    print(f"線程數: 5")
    print(f"智能重試: 啟用（最多5次）")
    print(f"基礎延遲: 0.8秒/請求")
    print(f"指數退避: 4秒→8秒→16秒→32秒→60秒")
    print("-"*60)
    
    success_count = 0
    error_count = 0
    throttle_count = 0
    
    start_time = time.time()
    
    for i, domain in enumerate(test_domains, 1):
        print(f"\n[{i}/{len(test_domains)}] 檢查: {domain}")
        
        try:
            result = hunter.check_single_domain(domain)
            
            if result:
                success_count += 1
                if result.get('available'):
                    print(f"  ✓ 可購買 - ¥{result.get('price', 0):.2f}")
                else:
                    print(f"  ✗ 已註冊")
            else:
                print(f"  ⚠️ 跳過（可能已檢查過）")
        except Exception as e:
            error_count += 1
            error_msg = str(e)
            if 'Throttling' in error_msg or 'flow control' in error_msg:
                throttle_count += 1
                print(f"  ⚠️ API限流（應該會自動重試）")
            else:
                print(f"  ❌ 錯誤: {error_msg}")
    
    elapsed = time.time() - start_time
    
    print("\n" + "="*60)
    print("測試結果")
    print("="*60)
    print(f"總域名數: {len(test_domains)}")
    print(f"成功檢查: {success_count}")
    print(f"錯誤數: {error_count}")
    print(f"觸發限流: {throttle_count}")
    print(f"總耗時: {elapsed:.1f}秒")
    print(f"平均速度: {len(test_domains)/elapsed:.2f}域名/秒")
    
    if error_count == 0:
        print("\n✅ 測試通過！API限流處理正常工作")
    elif error_count <= 2:
        print("\n⚠️ 測試基本通過，但有少量錯誤")
    else:
        print("\n❌ 測試未通過，請檢查網絡或API配置")
    
    print("="*60)

if __name__ == "__main__":
    try:
        test_throttling_fix()
    except KeyboardInterrupt:
        print("\n\n⚠️ 測試被用戶中斷")
    except Exception as e:
        print(f"\n❌ 測試失敗: {str(e)}")
        sys.exit(1)
