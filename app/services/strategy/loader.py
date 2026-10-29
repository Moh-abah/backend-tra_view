# app\services\strategy\loader.py
import json
import yaml
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import hashlib
from datetime import datetime
import tempfile
import importlib.util
import sys

from .schemas import StrategyConfig
from .core import StrategyEngine

class StrategyLoader:
    """محمل وإدارة الإستراتيجيات الديناميكية"""
    
    def __init__(self, strategies_dir: str = "strategies"):
        self.strategies_dir = Path(strategies_dir)
        self.strategies_dir.mkdir(exist_ok=True)
        
        # كاش للإستراتيجيات المحملة
        self._loaded_strategies: Dict[str, StrategyEngine] = {}
        self._strategy_hashes: Dict[str, str] = {}
        
        # سجل التغييرات
        self._change_log: List[Dict[str, Any]] = []
    
    def load_strategy_from_dict(self, strategy_dict: Dict[str, Any]) -> StrategyEngine:
        """
        تحميل إستراتيجية من قاموس
        
        Args:
            strategy_dict: قاموس يحتوي على تكوين الإستراتيجية
            
        Returns:
            StrategyEngine: محرك الإستراتيجية المحملة
        """
        # التحقق من صحة التكوين
        config = StrategyConfig(**strategy_dict)
        
        # تحديث وقت التعديل
        config.updated_at = datetime.utcnow()
        
        # إنشاء hash فريد للإستراتيجية
        strategy_hash = self._calculate_strategy_hash(strategy_dict)
        
        # التحقق إذا كانت الإستراتيجية محملة مسبقاً
        if strategy_hash in self._loaded_strategies:
            print(f"Strategy '{config.name}' already loaded from cache")
            return self._loaded_strategies[strategy_hash]
        
        # إنشاء محرك إستراتيجية جديد
        engine = StrategyEngine(config)
        
        # تخزين في الكاش
        self._loaded_strategies[strategy_hash] = engine
        self._strategy_hashes[config.name] = strategy_hash
        
        # تسجيل في سجل التغييرات
        self._log_change("load", config.name, strategy_hash)
        
        print(f"Strategy '{config.name}' loaded successfully")
        return engine
    
    def load_strategy_from_json(self, json_str: str) -> StrategyEngine:
        """
        تحميل إستراتيجية من JSON string
        
        Args:
            json_str: سلسلة JSON تحتوي على تكوين الإستراتيجية
            
        Returns:
            StrategyEngine: محرك الإستراتيجية المحملة
        """
        strategy_dict = json.loads(json_str)
        return self.load_strategy_from_dict(strategy_dict)
    
    def load_strategy_from_file(self, file_path: Union[str, Path]) -> StrategyEngine:
        """
        تحميل إستراتيجية من ملف
        
        Args:
            file_path: مسار الملف (JSON أو YAML)
            
        Returns:
            StrategyEngine: محرك الإستراتيجية المحملة
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Strategy file not found: {file_path}")
        
        # تحديد نوع الملف
        if file_path.suffix.lower() == '.json':
            with open(file_path, 'r', encoding='utf-8') as f:
                strategy_dict = json.load(f)
        elif file_path.suffix.lower() in ['.yaml', '.yml']:
            with open(file_path, 'r', encoding='utf-8') as f:
                strategy_dict = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
        
        # إضافة اسم الملف إذا لم يكن موجوداً
        if 'name' not in strategy_dict:
            strategy_dict['name'] = file_path.stem
        
        return self.load_strategy_from_dict(strategy_dict)
    
    def load_strategy_from_python(self, python_code: str, strategy_name: str) -> StrategyEngine:
        """
        تحميل إستراتيجية من كود Python
        
        Args:
            python_code: كود Python يحتوي على تعريف الإستراتيجية
            strategy_name: اسم الإستراتيجية
            
        Returns:
            StrategyEngine: محرك الإستراتيجية المحملة
        """
        # إنشاء ملف مؤقت
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            tmp.write(python_code)
            tmp_path = tmp.name
        
        try:
            # تحميل الموديول
            spec = importlib.util.spec_from_file_location(strategy_name, tmp_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[strategy_name] = module
            spec.loader.exec_module(module)
            
            # استخراج تكوين الإستراتيجية
            if hasattr(module, 'get_strategy_config'):
                strategy_dict = module.get_strategy_config()
            else:
                raise ValueError("Python strategy must have 'get_strategy_config()' function")
            
            return self.load_strategy_from_dict(strategy_dict)
        
        finally:
            # تنظيف الملف المؤقت
            Path(tmp_path).unlink(missing_ok=True)
    
    def save_strategy_to_file(
        self,
        strategy_config: StrategyConfig,
        file_name: Optional[str] = None
    ) -> Path:
        """
        حفظ إستراتيجية إلى ملف
        
        Args:
            strategy_config: تكوين الإستراتيجية
            file_name: اسم الملف (اختياري)
            
        Returns:
            Path: مسار الملف المحفوظ
        """
        if file_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{strategy_config.name}_{timestamp}.json"
        
        file_path = self.strategies_dir / file_name
        
        # تحويل إلى قاموس
        strategy_dict = strategy_config.dict()
        
        # حفظ كـ JSON
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(strategy_dict, f, indent=2, ensure_ascii=False)
        
        # تسجيل في سجل التغييرات
        self._log_change("save", strategy_config.name, str(file_path))
        
        return file_path
    
    def update_strategy(
        self,
        strategy_name: str,
        updates: Dict[str, Any]
    ) -> Optional[StrategyEngine]:
        """
        تحديث إستراتيجية محملة
        
        Args:
            strategy_name: اسم الإستراتيجية
            updates: التحديثات المطلوبة
            
        Returns:
            StrategyEngine: محرك الإستراتيجية المحدثة
        """
        strategy_hash = self._strategy_hashes.get(strategy_name)
        if not strategy_hash:
            print(f"Strategy '{strategy_name}' not found in cache")
            return None
        
        # الحصول على المحرك الحالي
        current_engine = self._loaded_strategies.get(strategy_hash)
        if not current_engine:
            return None
        
        # الحصول على التكوين الحالي
        current_config = current_engine.config.dict()
        
        # تطبيق التحديثات
        updated_config = {**current_config, **updates}
        updated_config['updated_at'] = datetime.utcnow()
        
        # إعادة تحميل الإستراتيجية
        new_engine = self.load_strategy_from_dict(updated_config)
        
        # تسجيل التحديث
        self._log_change("update", strategy_name, f"Updated with {len(updates)} changes")
        
        print(f"Strategy '{strategy_name}' updated successfully")
        return new_engine
    
    def get_strategy(self, strategy_name: str) -> Optional[StrategyEngine]:
        """
        الحصول على إستراتيجية محملة مسبقاً
        
        Args:
            strategy_name: اسم الإستراتيجية
            
        Returns:
            StrategyEngine أو None
        """
        strategy_hash = self._strategy_hashes.get(strategy_name)
        if strategy_hash:
            return self._loaded_strategies.get(strategy_hash)
        return None
    
    def list_loaded_strategies(self) -> List[Dict[str, Any]]:
        """سرد جميع الإستراتيجيات المحملة"""
        strategies = []
        
        for strategy_hash, engine in self._loaded_strategies.items():
            summary = engine.get_strategy_summary()
            summary["hash"] = strategy_hash[:8]  # أول 8 أحرف من الـ hash
            summary["loaded_at"] = self._get_load_time(strategy_hash)
            strategies.append(summary)
        
        return strategies

    def load_all_from_disk(self) -> Dict[str, Any]:
        """Bugfix: كانت /list فارغة دائماً لأن لا أحد يحمّل مجلد strategies/.

        يمسح المجلد ويحمّل كل ملفات JSON/YAML (الملفات الفاشلة تُسجَّل ولا
        تُوقف البقية). التحميل idempotent بفضل كاش الـ hash — الملفات المحملة
        مسبقاً لا تُعاد. يُرجع إحصاءات مبسطة للسجلات والـ API.
        """
        loaded, failed, skipped = 0, 0, 0
        files = sorted(
            list(self.strategies_dir.glob("*.json"))
            + list(self.strategies_dir.glob("*.yaml"))
            + list(self.strategies_dir.glob("*.yml"))
        )
        for path in files:
            try:
                # تجاهل الملفات الضخمة غير المعقولة (> 5MB) — ليست استراتيجيات
                if path.stat().st_size > 5 * 1024 * 1024:
                    skipped += 1
                    continue
                before = set(self._strategy_hashes.values())
                self.load_strategy_from_file(path)
                after = set(self._strategy_hashes.values())
                if after - before:
                    loaded += 1
                else:
                    skipped += 1  # محمّلة مسبقاً (نفس الـ hash)
            except Exception as e:  # noqa: BLE001 — ملف تالف لا يمنع البقية
                failed += 1
                print(f"StrategyLoader: failed to load {path.name}: {e}")
        result = {
            "dir": str(self.strategies_dir),
            "files_found": len(files),
            "newly_loaded": loaded,
            "already_loaded": skipped,
            "failed": failed,
        }
        print(f"StrategyLoader disk scan: {result}")
        return result
    
    def reload_strategy(self, strategy_name: str) -> Optional[StrategyEngine]:
        """
        إعادة تحميل إستراتيجية من الملف
        
        Args:
            strategy_name: اسم الإستراتيجية
            
        Returns:
            StrategyEngine: محرك الإستراتيجية المُعاد تحميله
        """
        strategy_hash = self._strategy_hashes.get(strategy_name)
        if not strategy_hash:
            print(f"Strategy '{strategy_name}' not found in cache")
            return None
        
        # البحث عن ملف الإستراتيجية
        strategy_files = list(self.strategies_dir.glob(f"*{strategy_name}*.json"))
        
        if not strategy_files:
            print(f"No strategy files found for '{strategy_name}'")
            return None
        
        # أخذ أحدث ملف
        latest_file = max(strategy_files, key=lambda x: x.stat().st_mtime)
        
        try:
            # إزالة من الكاش
            if strategy_hash in self._loaded_strategies:
                del self._loaded_strategies[strategy_hash]
            
            # إعادة تحميل
            return self.load_strategy_from_file(latest_file)
            
        except Exception as e:
            print(f"Error reloading strategy {strategy_name}: {e}")
            return None
    
    def _calculate_strategy_hash(self, strategy_dict: Dict[str, Any]) -> str:
        """حساب hash فريد للإستراتيجية"""
        # إزالة الحقول الديناميكية التي لا تؤثر على التنفيذ
        filtered_dict = {k: v for k, v in strategy_dict.items() 
                        if k not in ['created_at', 'updated_at', 'author']}
        
        # إنشاء سلسلة قابلة للتجزئة
        strategy_str = json.dumps(filtered_dict, sort_keys=True)
        
        # حساب SHA256 hash
        return hashlib.sha256(strategy_str.encode()).hexdigest()
    
    def _log_change(self, action: str, strategy_name: str, details: Any):
        """تسجيل تغيير في سجل التغييرات"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "strategy_name": strategy_name,
            "details": str(details)
        }
        self._change_log.append(log_entry)
        
        # حفظ فقط آخر 1000 تغيير
        if len(self._change_log) > 1000:
            self._change_log = self._change_log[-1000:]
    
    def _get_load_time(self, strategy_hash: str) -> Optional[str]:
        """الحصول على وقت تحميل الإستراتيجية"""
        for log in reversed(self._change_log):
            if log["action"] == "load" and strategy_hash[:8] in str(log.get("details", "")):
                return log["timestamp"]
        return None
    
    def get_change_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """الحصول على سجل التغييرات"""
        return self._change_log[-limit:] if self._change_log else []