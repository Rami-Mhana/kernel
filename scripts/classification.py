#!/usr/bin/env python3
"""
============================================================
Shared Classification Module for dahih-archive
============================================================
Unified taxonomy and two-pass classifier:
1. Deterministic rules / series detection (fast, no API)
2. External AI API adapter for ambiguous records (configurable)

Taxonomy is enriched with specific episode-topic keywords,
English description aliases, and proper-name detection.
============================================================
"""
from __future__ import annotations
import os
import json
import time
import re
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
from pathlib import Path

from content_schema import Episode, AuditStatus, normalize_arabic_text, clean_description_for_classification


# ============ TAXONOMY ============
# Single source of truth for categories and keywords.
# Each entry is a list of Arabic topic keywords specific to actual
# "الدحيح" episode titles, plus English aliases for description matching.
# Channel-specific overrides can be loaded from config file.

DEFAULT_TAXONOMY: dict[str, list[str]] = {
    "تاريخ": [
        # Core history concepts
        "تاريخ", "إمبراطورية", "دولة", "عصر", "قرون", "سلطنة", "مملكة", "جمهورية",
        "خلافة", "ملك", "سلطان", "خليفة", "أمير", "أميرة", "وزير",
        "ثورة", "انتقالي", "احتلال", "استعمار", "انتداب", "استقلال",
        "حرب", "معركة", "فتيحة", "حصار", "غزوة", "فتح",
        "مظالم", "إبادة", "إبادة جماعية",
        "جدار", "سور", "قلعة", "أهرام", "معبد", "كنيسة", "مسجد", "مدينة",
        # Historical periods
        "قرن", "قرن العشرين", "قرن الثامن", "قرن الخامس", "قرن السابع",
        "العصور الوسطى", "العصور الحديثة", "العربي", "العسكري",
        # Dynasties/civilizations
        "فاطمي", "أموي", "عباسي", "عثماني", "مملوكي", "صليبي", "مغولي", "فراعنة",
        "روماني", "بيزنطي", "إغريقي", "فارسي", "عربية", "إسلامية",
        # Dynasties specific (Arabic forms)
        "الفاطميون", "الأمويون", "العباسيون", "العثمانيون", "المماليك",
        "الرومان", "البيزنطيين", "المغول", "الفراعنة", "الإغريق",
        "الفارسية",
        # Historical events
        "نكبة", "نكسة", "كامب ديفيد", "أوسلو", "معاهدة", "اتفاقية",
        "الحرب العالمية", "أولى", "ثانية", "فيتنام", "كوريا",
        "الحرب الباردة", "الحرب الأهلية", "الثورة الفرنسية", "بريكست",
        "الانفصال", "الاستقلال", "التمرد", "الانتقال",
        "قرن الإذلال", "سقوط بغداد", "معركة ذي قار", "حرب البسوس",
        # Historical figures (proper names from episodes)
        "هتلر", "ستالين", "تشرشل", "روزفلت", "نابليون",
        "لينين", "بوتين", "ترامب", "ميركل", "أوباما", "كينيدي",
        "شابلن", "روبين ويليامز", "تيد كازينسكي", "كازينسكي",
        "سورغ", "ريتشارد سورغ", "ماركو بولو", "فلاديمير بوتين", "فلاديمير لينين",
        "نابليون", "جون كينيدي", "سيف الله المسلول",
        # Geographic
        "أيرلندا", "اليابان", "الصين", "روسيا", "الهند",
        "الجزائر", "المغرب", "أمريكا", "أوروبا", "آسيا", "إفريقيا",
        "الأندلس", "بولندا", "ألمانيا", "النرويج", "السويد", "فرنسا",
        "البرتغال", "اليونان", "تركيا", "إيران", "مصر", "العراق", "بغداد",
        # Structures/landmarks
        "برج إيفل", "تاج محل", "أهرامات", "أبو الهول",
        "مدائن صالح", "قصر الحمراء", "تاج محل", "الهرم", "أهرامات",
        # Specific episode topics
        "إسبرطة", "جيش", "مجتمع", "أمة", "أسطول أصفر", "صعود أوبر",
        "القتل بسبب الرفض", "بلاك ووتر", "غسيل أموال", "سؤال 64 دولار",
        "ريتشارد سورغ", "جاسوس", "تاريخ الإعدام", "العبودية",
        "استقلال الجزائر", "الثورة الفرنسية", "هتلر ستالين", "عدو الزعيم ستالين",
        "الذهب", "دراكولا", "العمارة التي قاومت النازيين", "لوحة شادي عبدالسلام",
        "هدنة عيد الميلاد", "مديرون أشرار", "فلوس الأغنياء", "الحرب العالمية الأولى",
        "أهم تاكسي", "جنكستان", "قانون الغابة", "الفراعنة", "روسيا", "حرب فيتنام",
        "هتلر", "الحروب", "النووي والبكيني", "قصة فورد", "قصر الحمراء", "تاريخ المطبخ",
        "الملحمة العربية", "حرب البسوس", "الطاعون الأسود", "اكتشاف مقبرة توت",
        # English keywords for descriptions
        "history", "historical", "empire", "war", "battle", "dynasty",
        "civilization", "pharaoh", "roman", "byzantine", "ottoman",
        "world war", "revolution", "independence", "colonialism",
        "hitler", "stalin", "napoleon", "lenin", "putin", "kennedy",
        "spy", "sorge", "marco polo", "alexandria", "tutankhamun",
    ],
    "علوم": [
        # Biology / Life sciences
        "علم", "علوم", "أحياء", "وراثة", "وراثي", "جينات", "جين", "جينوم",
        "خلية", "بروتين", "حمض", "حمض نووي", "DNA", "الحمض النووي",
        "تكاثر", "تلقيح", "انقسام", "نسيل", "تطور",
        "انتخاب طبيعي", "داروين", "مندل", "وراثة",
        "نبات", "نباتات", "حيوان", "حيوانات", "كائن", "كائنات",
        "حياة", "مخلوق", "مخلوقات", "كائن حي", "كائنات حية",
        "انقراض", "مهدد", "نوع", "أنثى", "ذكر",
        "زومبي", "وحش", "وحوش", "خلقة", "مخلوق",
        # Evolution / anthropology
        "تطور", "أصل البشر", "أصل", "بشر", "إنسان", "بشرية", "تطوري",
        # Animals / nature (from actual episodes)
        "حيوان", "حيوانات", "حشرة", "حشرات", "طائر", "طيور", "سمك", "أسماك",
        "ثعبان", "أفعى", "تمساح", "تمساح مجنح", "بطريق",
        "فيل", "أسد", "قط", "بطة", "دجاج", "دجاجة",
        "خفاش", "خفافيش", "شعلة",
        "كلب", "قلب الكلب", "كلاب",
        "قطة", "قطط",
        "نملة", "نمل", "نحل", "نحلة",
        "عصفور", "غراب", "ديك", "حمامة",
        "سمكة قرش", "قرش",
        "صيد", "صياد",
        "بيئة", "طبيعة", "مناخ", "غابة",
        "نظام إيكولوجي", "سلسلة غذائية", "تكافؤ", "تنازع",
        # Specific animals from episodes
        "أخطبوط", "دولفين", "أزرق", "باندا", "صرصور", "حصان", "ثعبان",
        "طائر", "طيران", "طيور", "هجرة",
        # Physics
        "فيزياء", "كيمياء", "جيولوجيا", "فلك", "فضاء",
        "ناسا", "قمر", "مريخ", "مجرة", "كوكب", "أرض", "شمس",
        "نجوم", "نجم", "سطوع",
        "ثقب أسود", "ثقب دودي", "مادة مظلمة", "طاقة مظلمة",
        "نسبية", "كم", "كمي", "ميكانيكا كمومية",
        "ذرة", "جسيم", "فوتون", "إلكترون", "بروتون", "نيوترون",
        "طاقة", "مادة", "موجة",
        "ضوء", "صوت", "حرارة", "كهرباء", "مغناطيس",
        "ليزر", "بلازما", "مشع", "أشعة",
        "زجاج", "سيليكا", "رماد", "حمم بركانية",
        "معادن", "معدن", "سيليكون",
        # Chemistry
        "كيمياء", "مركب", "عنصر", "تفاعل", "كاتاليزر",
        "أحماض", "قواعد", "أحماض نووية", "جزيئة", "جزيئات",
        "كربون", "عنصر الكربون",
        # Astronomy / Space (from episodes)
        "فضاء", "محطة فضاء", "محطة الفضاء الدولية",
        "المجموعة الشمسية", "المجرة", "النجوم",
        "أشعة كونية", "رعب نووي", "قنبلة نووية", "مادة مضادة",
        "ثقب دودي", "كون", "مصير الأرض", "الشمس",
        # Materials / technology
        "بلاستيك", "بلاستيكي", "مواد", "مواد معدنية", "معادن",
        "زجاج", "كيف غيّر الزجاج", "رقاقة", "شريحة",
        # Episode-specific topics
        "زومبي", "الوحوش", "أبطأ كائن", "أطول نفس",
        "الخلية العصبية", "علم الوراثة", "البيولوجيا الكمية",
        "كمبيوترات حية", "إحياء الموتى", "الخلايا الجذعية",
        "الانقراض", "النشاط الإشعاعي", "إشعاع",
        # English keywords for descriptions
        "zombie", "zoology", "biology", "evolution",
        "species", "genus", "animal", "animals", "plants",
        "ecosystem", "ecology", "biodiversity", "extinction",
        "fossil", "prehistoric", "dinosaur",
        "mammal", "primate",
        "genetics", "genome", "chromosome", "cell",
        "protein", "enzyme", "molecule", "atoms",
        "physics", "quantum", "relativity",
        "gravity", "optics", "laser",
        "chemistry", "chemical", "reactions", "compounds",
        "space", "astronomy", "astronaut",
        "galaxy", "planet", "planets",
        "nebula", "cosmic", "black hole",
        "biome", "habitat",
        "morphology", "anatomy", "physiology",
        "neural", "nervous system",
        "biochemistry", "molecular", "cellular", "microscopic",
        "biologist", "biomedical",
        "marine", "ocean", "oceanic",
        "environmental", "wildlife", "predator", "prey",
        "photosynthesis", "respiration", "metabolism",
        "octopus", "dolphin", "panda", "bat", "cockroach",
        "cosmic rays", "nuclear", "antimatter", "wormhole",
    ],
    "رياضيات": [
        "رياضيات", "رياضي", "عدد", "أرقام", "حساب", "هندسة",
        "جبر", "تفاضل", "تكامل", "مشتقة",
        "مصفوفة", "متجه", "أبعاد", "بعد",
        "احتمال", "إحصاء", "توزيع",
        "نظرية", "مبرهنة", "قانون", "مقادير",
        "خوارزمية", "تعقيد", "ترميز", "تشفير",
        "بت", "بايت", "رقمي", "رقمية",
        "بايز", "قاعدة بايز",
        "بواسون", "توزيع بواسون",
        "بنفورد", "قانون بنفورد",
        "إحصاء", "إحصائيات",
        "نسبة", "نسب",
        "معادلة", "معادلات",
        "متباينة", "متباينات",
        "دالة", "دوال",
        "مشتق", "مشتقات",
        "متعدد حدود", "متعدد",
        "متكامل", "تكامل",
        "مصفوفات", "متجهات",
        "منحنى", "منحنيات",
        "رسم بياني",
        "عشوائي", "عشوائية",
        "احتمال", "احتمالات",
        "استنتاج", "تقدير",
        "تحليل", "تحليلي",
        "رمزي", "رموز",
        "منطقي", "لوجيك", "منطق",
        "ديراك", "دلتا",
        # Specific episode topics
        "3.14159", "باي", "π",
        "العد", "العدد", "الأعداد",
        "صفر", "واحد", "اثنين", "ثلاثة", "أربعة", "خمسة",
        "لا نهائي", "لانهاية", "ما لا نهاية",
        "كونين", "لامينا",
        "موازاة", "التوازي", "التوازي العلمي",
        "الرياضيات المحرمة", "محرمات", "مجموعة ماندلبروت",
        "فيبوناتشي", "النسبة الذهبية", " frattali",
        # English keywords for descriptions
        "math", "mathematics", "geometry", "algebra", "calculus",
        "statistics", "probability", "theorem", "equation",
        "infinity", "infinite", "pi", "π",
        "prime number", "prime numbers",
        "fractal", "fractals", "golden ratio", "mandelbrot",
        "fibonacci", "binary", "decimal",
        "statistics", "statistic", "data analysis",
        "statistical", "statistically",
        "benford", "benford's law", "poisson", "bayes", "bayesian",
    ],
    "تقنية وذكاء اصطناعي": [
        "تقنية", "تكنولوجيا", "حاسوب", "كمبيوتر",
        "برمجة", "كود", "خوارزمية", "ذكاء اصطناعي",
        "تعلم آلي", "تعلم عميق", "شبكة عصبية",
        "GPT", "LLM", "ترانسفورمر", "محول",
        "بيانات", "سحابة", "بلوك تشين",
        "عملة مشفرة", "بيتكوين", "إيثيريوم", "Web3",
        "ميتافيرس", "واقع افتراضي", "واقع معزز",
        "روبوت", "أتمتة", "سيبراني",
        "أمن معلومات", "اختراق", "خصوصية", "مراقبة",
        "فيسبوك", "جوجل", "أمازون", "مايكروسوفت", "أبل",
        "تسلا", "سبيس إكس", "أوبن أيه آي", "أنثروبيك", "ديب مايند",
        # Specific episode topics
        "تيك توك", "تيك توك",
        "تويتر", "إكس", "X",
        "إنستغرام",
        "عملة الفيسبوك", "ليبريس",
        "تسلا", "سبيس إكس", "إيلون ماسك", "بدايات إيلون ماسك",
        "التعويذة الخوارزمية", "خوارزمية", "تعلم الآلة",
        "القرصنة", "هاكرز", "اختراق",
        "كيف تصنع الترند", "ترند", "فيرال",
        "بونو تيتش", "يوتيوب", "تيك توك",
        "ستارت أب", "شركات ناشئة", "ريادة",
        "الرقاقة الخطيرة", "شريحة", "أشباه موصلات",
        "الهاتف الذكي", "هاتف", "ذكي",
        # English keywords for descriptions
        "artificial intelligence", "machine learning",
        "deep learning", "neural network", "neural networks",
        "algorithm", "algorithms", "software", "hardware",
        "computing", "computer", "computers",
        "programming", "code", "coding",
        "technology", "technological", "tech",
        "digital", "data", "big data",
        "cloud", "cloud computing", "cloud-based",
        "blockchain", "crypto", "cryptocurrency",
        "bitcoin", "ethereum", "web3",
        "metaverse", "virtual reality", "augmented reality",
        "robot", "robots", "robotics", "automation",
        "cybersecurity", "information security", "privacy",
        "surveillance", "hacking", "hacker",
        "facebook", "google", "amazon", "microsoft", "apple",
        "tesla", "spacex", "space x",
        "openai", "anthropic", "deepmind",
        "AI", "ML", "NLP",
        "LLM", "LLMs", "GPT", "Transformer",
        "startup", "start-up", "venture",
        "innovation", "innovator", "disruptive", "disruption",
        "application", "applications", "app", "apps",
        "internet", "web", "web2", "web3",
        "social media", "social network", "platform",
        "algorithmic", "algorithm", "developer",
        "software engineer", "tiktok", "instagram", "twitter",
    ],
    "طب وصحة": [
        # Core medical terms
        "طب", "صحة", "مرض", "علاج", "دواء", "جراحة", "طبيب", "مستشفى",
        "سرطان", "ورم", "ورمي",
        "فيروس", "بكتيريا", "عدوى", "مناعة", "لقاح",
        "جائحة", "وباء", "كورونا", "كوفيد", "إنفلونزا",
        "تسمم", "غثيان", "قيء", "إسهال", "تشنج",
        "ألم", "توغل", "توسع", "تضخم",
        "قلب", "دماغ", "عصب", "عقل", "دم",
        "رئة", "كلى", "كبد", "معدة", "أمعاء", "قولون",
        "معوي", "خصي",
        "عصبي", "أعصاب", "عصبية",
        "نوم", "يقظ", "نعاسة", "إرهاق",
        "تغذية", "طعام", "وجبة", "أكلة", "أكل",
        "سمنة", "رشح", "تدخين", "خمور", "مشروب",
        "حميات", "حمية", "رجيم",
        "فيتامين", "معدن", "سمن", "دهون",
        "كربوهيدرات", "بروتين", "ألياف",
        "جرعة", "جرعات",
        "تطعيم", "لقاح", "لقاحات",
        "جرثومة", "جراثيم", "جرثومي",
        "طفيلية", "طفيليات",
        "فطريات", "فطر", "فطرية",
        "بكتيريا", "بكتيري",
        "فيروسات", "فيروسية",
        "أورام", "ورم", "سرطان",
        "خلايا", "خلية", "خلوية",
        "دم", "دمي", "أوردة", "عروق",
        "ضغط", "غدد", "صماء",
        "تنفس", "تنفسي",
        "مخ", "دماغ", "دماغي",
        "قلب", "أوعية", "شرايين",
        "كلى", "كلوي",
        "كبد", "كبدي",
        "رئة", "رئوي",
        "عين", "عينين",
        "أذن", "أذنين",
        "أنف",
        "فم", "لسان", "لثة",
        "أسنان", "ضرس",
        "شعر",
        "بشرة", "جلد",
        "عرق", "عرقي",
        "حركة", "حركية",
        "وظائف", "وظيفة",
        "مرض", "أمراض", "مرضي",
        "مصل", "مصلات",
        "مضاد", "مضادات",
        "مضاد حيوي", "مضادات حيوية",
        "مسكن", "مسكنات",
        "علاج", "علاجات", "علاجي",
        "جراحة", "جراح",
        "اختبار", "اختبارات",
        # Conditions
        "نوبة", "نوبات", "صرع", "صرعية",
        "خرف",
        "سكري", "سكري",
        "سكرية", "سكريات",
        # Mental health
        "نفسي", "نفسية", "نفسيات",
        "اكتئاب", "قلق", "توحد", "فرط حركة",
        "إدمان", "تدخين",
        "مخدر", "مخدرات",
        "توتر", "رهبة", "فوبيا", "خوف",
        # Specific episodes (from actual data)
        "هبد", "الهبد",
        "قولون", "القولون",
        "شوربة الخفافيش", "خفافيش",
        "الإنفلونزا الإسبانية", "إنفلونزا",
        "كورونا", "كوفيد", "كوفيد-19",
        "التدخين", "التدخين والسرطان",
        "السرطان", "أقدم مرض",
        "الأمراض اليتيمة", "أمراض يتيمة",
        "الوسواس", "الوسواس القهري", "وسواس",
        "المسكنات", "مسكنات", "مسكن",
        "الحساسية", "حساسية", "حساسية المياه",
        "الضغط العصبي", "ضغط عصبي",
        "الصلع",
        "الدواء والغلاء", "غلاء الأدوية",
        "التطعيم", "تطعيم",
        "خطر الكلب",
        "الحياة في زمن الكورونا", "جائحة كورونا",
        "الموت", "ليه بنموت",
        "الولادة", "رحلة التسعة شهور",
        "الحبة الزرقاء",
        "العلاج بالصلصة",
        "أم جرثوم",
        "من خاف سلم",
        "الصيام", "ليه بنتخن في رمضان",
        "الخلية العصبية جداً",
        "العلاج المناعي", "مناعة",
        "الانقراض", "خلايا جذعية",
        "محاكمة الطب الجنائي", "طب جنائي",
        "هرمون", "هرمون مظلوم",
        "أين ذهب الكرش", "سمنة", "بدانة",
        # English keywords for descriptions
        "cancer", "carcinoma", "tumor",
        "virus", "viral", "infection", "infectious",
        "immune", "immunity", "vaccine", "vaccination",
        "pandemic", "epidemic", "disease", "diseases",
        "corona", "covid", "covid-19", "covid19", "sars",
        "flu", "influenza",
        "health", "healthcare",
        "medicine", "medical", "doctor", "doctors", "hospital",
        "treatment", "treat", "therapy", "therapies",
        "drug", "drugs", "medication", "medications",
        "surgery", "surgical",
        "diagnosis", "diagnostic", "diagnose",
        "patient", "patients",
        "clinical", "clinic", "clinical trial",
        "symptom", "symptoms",
        "syndrome", "syndromes",
        "physician", "nurse", "nurses", "nursing",
        "illness", "sickness",
        "pain", "painful",
        "chronic", "acute",
        "diabetes", "diabetic",
        "heart", "cardiac", "heart disease",
        "stroke", "brain", "neurological",
        "obesity", "obese",
        "smoking", "tobacco", "nicotine",
        "nutrition", "diet", "dietary",
        "vitamin", "vitamins",
        "supplement", "supplements",
        "mineral", "minerals",
        "protein", "carbohydrate", "fat",
        "fasting", "fast",
        "sleep", "sleep disorder",
        "fatigue", "exhaustion",
        "treatment", "treatments",
        "diagnosis", "diagnostics",
        "anatomy", "physiology",
        "pathology", "oncology", "oncologist",
        "cardiology", "cardiologist",
        "neurology", "neurologist",
        "geriatrics", "pediatric", "pediatrics",
        "psychiatry", "psychiatrist",
        "psychology", "psychologist",
        "psychotherapy", "therapy",
        "addiction", "addict",
        "anxiety", "depression", "depressive",
        "autism", "autism spectrum",
        "ADHD", "adhd",
        "mental health", "mental",
        "immunotherapy", "stem cells", "forensic medicine",
    ],
    "علم نفس واجتماع": [
        # Core psychology
        "نفس", "سيكولوجي", "سلوك", "عقل", "لاوعي",
        "فرويد", "يونغ", "سلوكية", "معرفية",
        "شخصية", "اضطراب", "مرض نفسي", "علاج نفسي",
        "تحليل", "نفسي", "تحليلي",
        "حلم", "رمز", "أسطورة",
        # Social sciences
        "اجتماع", "مجتمع", "ثقافة", "عادة", "تقليد",
        "زواج", "طلاق", "أسرة", "طفل", "تربية",
        "تعليم", "مدرسة", "جامعة", "عمل", "بطالة",
        "فقر", "ثراء", "طبقة", "تمييز",
        "عنصرية", "نسوية", "جنس", "هوية",
        "انتماء", "وحدة", "عزلة",
        "صداقة", "حب", "عنف", "تنمر",
        "رفض", "قبول", "ثقة", "خيانة",
        "غيرة", "كراهية",
        # Specific episodes (from actual data)
        "تعاطف", "التعاطف",
        "وحدة", "الوحدة",
        "رفض", "الرفض",
        "البقاء",
        "اللانهائية",
        "الوسواس", "الوسواس القهري",
        "النرجسية", "نرجسية",
        "الصدفة", "صدفة",
        "الذكاء الغبي", "غبي",
        "المزاج", "مزاج",
        "المراهقة", "مراهق",
        "الوعي", "لاوعي",
        "الشخصية", "شخصية",
        "السلوك", "سلوكيات",
        "الاجتماعي", "مجتمع",
        "الفرد", "فرد",
        "الجماعة", "جماعة",
        "الطفل", "أطفال",
        "المرأة", "مرأة",
        "الرجل", "رجل",
        "الأسرة", "أسرة",
        "الزواج", "زواج",
        "الطلاق", "طلاق",
        "التعليم", "تعليم",
        "البطالة", "بطالة",
        # Psychology-specific
        "تحفيز", "تعلم",
        "ذاكرة", "تذكر", "نسيان",
        "خوف", "رعب",
        "قلق", "اكتئاب",
        "توحد", "فرط حركة",
        "إدمان",
        "تشتت", "تركيز",
        "توتر", "ضغط", "ضغط عصبي",
        "عصبية",
        "نفسي", "نفسية", "نفسيات",
        "معرفي", "معرفية", "عقلية",
        "مفارقة المساجين", "معضلة المساجين",
        "الذاكرة الكاذبة", "ذاكرة",
        "الحب على النت", "علاقات", "إنترنت",
        "علاقات سامة", "سمية",
        "يا محاسن الصدف", "صدفة",
        "في مدح الكسل", "كسل",
        "مدمن نجاحات", "نجاح", "إدمان",
        "الصدمة", "صدمة",
        "بحث عن عدو", "عدو",
        "كومباوند الفئران", "فئران", "تجربة",
        # English keywords
        "psychology", "psychological", "psychologist",
        "psychotherapy", "psychiatric", "psychiatry",
        "behavior", "behavioral", "behaviorism",
        "cognition", "cognitive", "cognitively",
        "personality", "personality traits",
        "consciousness", "unconscious",
        "therapy", "therapeutic", "therapist",
        "mental health", "mental illness",
        "social", "society", "sociology",
        "anthropology", "culture",
        "child", "childhood", "children",
        "parent", "parenting", "parents",
        "family", "marriage", "divorce",
        "relationship", "relationships",
        "trauma", "traumatic", "PTSD",
        "addiction", "addict",
        "anxiety", "depression", "depressive",
        "autism", "autism spectrum",
        "ADHD", "adhd",
        "mental health",
        "conformity", "obedience", "authority",
        "milgram", "milgram experiment",
        "stanley", "social psychology",
        "social influence", "social norms",
        "collective behavior", "group", "groups",
        "stigma", "prejudice", "discrimination",
        "racism", "sexism",
        "identity", "belonging", "attachment",
        "emotion", "emotional", "emotions",
        "motivation", "persuasion", "compliance",
        "bias", "cognitive bias", "confirmation bias",
        "attention", "memory", "forgetting",
        "learning", "development", "developmental",
        "marshmallow", "marshmallow test",
        "prisoner's dilemma", "game theory",
    ],
    "اقتصاد وأعمال": [
        # Core economics
        "اقتصاد", "مال", "بنك", "عملة",
        "دولار", "يورو", "جنيه", "ريال", "درهم",
        "تضخم", "كساد", "أزمة", "مالية",
        "سوق", "بورصة", "سهم", "سند",
        "صندوق", "استثمار", "تمويل",
        "قرض", "فائدة", "ربا",
        "مصرف", "مركزي", "سياسة نقدية",
        "ميزانية", "عجز", "دين",
        "ناتج محلي", "نمو", "بطالة",
        "أجر", "راتب", "ضريبة",
        "جمارك", "تجارة", "تصدير",
        "استيراد", "عولمة",
        "شركة", "مؤسسة", "ريادة",
        "مشروع", "بزنس", "ستارت أب",
        "ريادي", "مستثمر", "رأس مال",
        "مخاطرة", "ربح", "خسارة",
        "ربحية", "تكلفة", "فائدة",
        # Specific episodes (from actual data)
        "بلاك ووتر", "شركات أمنية", "حرب", "تجارة",
        "غسيل الأموال", "غسيل", "أموال",
        "فلوس الأغنياء", "فلوس", "أغنياء",
        "الدولار", "عملة",
        "البزنس الذكي", "بزنس",
        "ستارت أب", "ستارت أب", "ريادة",
        "التأمين", "تأمين",
        "جيل زد", "جيل",
        "الاستثمار", "استثمار",
        "الوقود", "وقود", "نفط", "بترول",
        "الدين", "ديون", "إفلاس", "إفلاس الدول",
        "البطالة", "بطالة",
        "ماركو بولو", "تجارة", "طريق الحرير",
        "صعود أوبر", "أوبر", "اقتصاد مشاركة",
        "التنمية الاقتصادية", "تنمية",
        "تجارة الأفكار", "أفكار",
        "جماعة الإخوة الفيثاغورثيين", "رياضيات", "تاريخ",
        "الأزمة العالمية 2008", "أزمة", "2008",
        "لعنة البترول", "بترول", "نفط",
        "مفارقة الإنستغرام", "إنستغرام", "اقتصاد اهتمام",
        "كوفيد", "اقتصاد", "جائحة",
        # English keywords
        "economy", "economic", "economics",
        "finance", "financial", "financing",
        "money", "monetary",
        "bank", "banking", "banker", "banks",
        "currency", "currencies", "foreign exchange",
        "inflation", "hyperinflation",
        "recession", "depression", "crisis",
        "market", "stock market",
        "stocks", "shares", "stock exchange",
        "investment", "invest", "investor",
        "investing",
        "capital", "capitalism", "capitalist",
        "profit", "profits", "profitable",
        "loss", "losses",
        "trade", "trading", "export",
        "import", "imports",
        "business", "businesses",
        "corporate", "corporation", "company",
        "companies",
        "enterprise", "entrepreneur",
        "startup", "start-up", "venture",
        "venture capital", "VC",
        "price", "pricing", "prices",
        "cost", "costs", "cost-of-living",
        "wage", "wages", "salary",
        "rent", "rent-seeking",
        "tax", "taxes", "taxation",
        "tariff", "tariffs", "customs",
        "debt", "debts", "debt crisis",
        "credit", "debit", "loan",
        "interest rate", "interest",
        "dollar", "euro", "pound", "yen",
        "gold", "silver", "precious metals",
        "stock market", "stock exchange",
        "NASDAQ", "NYSE", "Dow Jones",
        "globalization", "global",
        "capitalism", "capitalist",
        "communism", "communist",
        "socialism", "socialist",
        "market economy", "planned economy",
        "free market", "free enterprise",
        "competition", "competitive",
        "monopoly", "monopolies",
        "oligarch", "oligarchs", "oligarchy",
        "wealth", "wealthy",
        "poverty", "poor",
        "inequality",
        "blackwater", "private military", "mercenary",
        "money laundering", "uber", "gig economy",
        "oil curse", "petroleum", "2008 crisis",
    ],
    "فلسفة ومنطق": [
        "فلسفة", "منطق", "حجة", "استدلال",
        "استنتاج", "مقدمة", "نتيجة", "قياس",
        "سيلوجزم", "أرسطو", "أفلاطون", "سقراط",
        "ديكارت", "كانط", "هيغل", "نيتشه",
        "سارتر", "كامو", "وجودية", "ظاهراتية",
        "تحليلية", "تحليلي",
        # Ethics / values
        "أخلاق", "قيمة", "خير", "شر",
        "عدالة", "حرية", "إرادة", "قدر",
        "معنى", "عبث", "لاجدوى",
        "أمل", "يأس", "حقيقة", "وهم",
        "معرفة", "إبستيمولوجيا", "أنطولوجيا",
        "ميتافيزيقا", "جمال", "ذوق", "إبداع",
        # Existence / meaning
        "وجود", "وجودي", "وجودية",
        "هوية", "ذات", "ذاتية",
        "حرية", "إرادة", "اختيار",
        "قدر", "مقدر", "مصير", "قضاء",
        "حظ", "مصير", "قضاء",
        "عبث", "لاأخلاق",
        # Specific episodes (from actual data)
        "المعنى", "معنى", "معنى الحياة",
        "اللانهائية", "لانهاية",
        "البقاء",
        "الذكاء الغبي", "غبي",
        "النرجسية", "نرجسية",
        "النهائية",
        "الوسطي الجميل", "وسطي",
        "الرأي الآخر",
        "المفروض مرفوض",
        "العزلة", "وحدة",
        "الهوية", "الاختيار",
        "المسؤولية", "اعتداء", "عنف",
        "العدل", "الإنسان",
        "الموت", "ليه بنموت",
        "الروح", "المادة", "الذات",
        "العمل", "الحب", "الهواء", "الأرض",
        "كيف تصنع قيمة من لا شيء", "قيمة", "لا شيء",
        "يوتيوبيا", "يوتوبيا", "مثالية",
        "فضيلة الأنانية", "أنانية",
        "هل الحيوانات تحلم", "أحلام", "وعي",
        "في مدح الكسل", "كسل",
        # English keywords
        "philosophy", "philosophical", "philosopher",
        "logic", "logical", "logically",
        "ethics", "ethical", "ethically",
        "moral", "morality",
        "good", "evil",
        "justice",
        "freedom", "free will",
        "determinism", "deterministic",
        "existentialism", "existential",
        "phenomenology", "phenomenological",
        "epistemology", "epistemological",
        "ontology", "ontological",
        "metaphysics", "metaphysical",
        "aesthetics", "aesthetic",
        "immoral", "virtue", "vice",
        "meaning", "meaning of life", "life meaning",
        "truth", "reality", "real", "realistic",
        "illusion", "illusions",
        "knowledge", "reason", "reasoning",
        "argument", "arguments", "debate",
        "nihilism", "nihilist",
        "absurd", "hope", "despair",
        "consciousness", "conscious",
        "soul", "spirit", "spiritual",
        "mind", "matter",
        "free will", "determinism",
        "utopia", "utopian", "egoism", "altruism",
    ],
    "لغة وآداب": [
        # Language
        "لغة", "عربي", "إنجليزي", "فرنسي", "ألماني",
        "صيني", "ياباني", "إسباني", "برتغالي",
        "نحو", "صرف", "إعراب",
        "بلاغة", "شعر", "نثر",
        "قصة", "رواية", "مسرحية", "ملحمة",
        "كاتب", "شاعر", "أديب", "ناقد",
        "نقد", "نقدي",
        "أسلوب", "صورة", "استعارة",
        "تشبيه", "كناية", "مجاز",
        "حقيقة", "رمز", "إشارة",
        "دال", "مدلول", "سيمياء",
        "لسانيات", "فونولوجيا",
        "مورفولوجيا", "سينتاكس",
        "براغماتية", "تداولي",
        "خطاب", "نص", "سياق",
        "ترجمة", "ترجم", "مترجم",
        # Specific episodes (from actual data)
        "اللغة العربية", "لغة عربية",
        "طريقة عمل اللغة",
        "شبابيك اللغة",
        "قاتل الكلمات", "سفاح اللغات",
        "لماذا لا نتحدث نفس العربية", "عربية",
        "الخطابة", "خطاب",
        "الكتاب", "مكتبة",
        "الكتابة", "القراءة",
        "كيف تكتب حلقة", "كتابة",
        "اللهجة", "لهجات",
        "العربية", "عربية",
        "إبادة الكتب", "كتب", "مكتبات",
        "المجاز والجواز", "مجاز", "جواز",
        "قصة القصة", "قصة", "سرد",
        "أجمل خيانة في تاريخ الأدب", "خيانة", "أدب",
        "لوحة شادي عبدالسلام", "سينما", "سينمائي",
        # English keywords
        "language", "linguistics", "linguistic",
        "arabic", "English", "French", "German", "Spanish",
        "Chinese", "Japanese", "Italian",
        "grammar", "syntax", "morphology",
        "semantics", "pragmatics",
        "semiotics", "semiotic",
        "rhetoric", "rhetorical",
        "translation", "translate", "translated",
        "translator", "interpreter",
        "literature", "literary",
        "novel", "novels", "novelist",
        "poetry", "poem", "poems", "poet", "poets",
        "fiction", "fictional", "fiction writer",
        "story", "storytelling", "narrative", "narrator",
        "author", "writer", "writers",
        "book", "books", "reading", "read",
        "text", "textual", "word", "words",
        "sentence", "sentences", "paragraph",
        "essay", "essays", "dictionary",
        "lexicon", "lexicography", "phrase",
        "metaphor", "metaphorical", "simile",
        "symbol", "symbolic", "symbolism",
        "imagery", "stylistics", "stylistic",
        "discourse", "communication",
        "sign language", "semiotics",
        "book burning", "censorship",
    ],
    "فنون وإعلام": [
        # Visual arts
        "فن", "رسم", "نحت", "عمارة", "معمار",
        "موسيقى", "غناء", "آلة", "أوركسترا", "سمفونية", "أوبرا",
        "باليه", "رقص", "رقصات",
        # Media
        "مسرح", "سينما", "فيلم",
        "مخرج", "ممثل", "سيناريو",
        "إنتاج", "إخراج", "تصوير",
        "مونتاج", "صوت", "إضاءة",
        "ديكور", "ملابس", "ماكياج",
        "إعلام", "صحافة", "إذاعة",
        "تلفزيون", "إنترنت",
        "سوشيال", "ميديا", "ترند", "فيرال", "مؤثر",
        "يوتيوب", "تيك توك", "إنستغرام", "تويتر", "فيسبوك", "بودكاست",
        "تدوين", "مدونة",
        # Specific episodes (from actual data)
        "ناطحات سحاب", "سحاب", "ناطحة", "عمارة",
        "الرجل العنكبوت", "سبايدرمان", "عنكبوت", "بطل خارق",
        "فيلم العيد", "عيد",
        "فيديوهات", "فيديو", "تيك توك", "تيك",
        "بونو تيتش", "يوتيوب", "صناعة محتوى",
        "الكوميديا", "كوميدي", "كوميديا", "الدحيح كوميدي",
        "الموناليزا", "موناليزا", "لوحة", "أشهر لوحة",
        "التنس", "تنس", "فورمولا", "فورمولا 1",
        "كرة القدم الأمريكية", "NFL", "ميسي", "نيمار",
        "كرة القدم", "كرة قدم", "كرة اليد", "يد",
        "مانشستر يونايتد", "مانشستر", "بوتشر", "بوتشريني",
        "سوبر هيروز", "هيرو", "هيروز", "أبطال خارقين",
        "أفلام رعب", "رعب", "فيلم رعب", "كابوس",
        "أغنية", "أغاني", "موسيقى", "أوركسترا", "سمفونية",
        "غناء", "مغني", "مغنية",
        "لعبة", "ألعاب", "لعبة واحدة", "مباراة", "مباريات",
        "تيكي تاكا", "كرة قدم", "تيكي تاكا",
        "حرب كرة القدم", "حرب", "كرة قدم",
        "ظاهرة كريم بنزيمة", "بنزيمة", "لاعب",
        "فيلم ثقافي", "ثقافي",
        # English keywords
        "art", "arts", "artistic", "drawing", "painting",
        "sculpture", "architecture", "architectural",
        "music", "musical", "song", "songs", "songwriter",
        "singer", "singers", "dance", "dancing", "dancer",
        "ballet", "opera", "theater", "theatre", "theatrical",
        "film", "films", "movie", "movies", "cinema", "cinematic",
        "director", "actor", "actress", "actors", "actresses",
        "acting", "performance", "screenplay", "script",
        "production", "producer", "edit", "editing", "editor",
        "cinematography", "camera", "sound", "soundtrack",
        "design", "designer", "media", "journalism", "journalist",
        "press", "news", "broadcast", "broadcasting",
        "radio", "podcast", "podcasts", "podcasting",
        "social media", "social network", "influencer",
        "influencers", "viral", "trend", "trending",
        "meme", "memes", "meme culture", "YouTube",
        "TikTok", "Instagram", "Twitter", "content creator",
        "digital media", "entertainment", "comedy", "comic",
        "funny", "comedy show", "spiderman", "superhero",
        "skyscraper", "architecture", "messi", "neymar",
        "manchester united", "formula 1", "f1",
    ],
    "بيئة وطبيعة": [
        "بيئة", "طبيعة", "مناخ", "طقس",
        "احتباس", "حراري", "كربون",
        "انبعاث", "تلوث",
        "هواء", "ماء", "تربة",
        "غابة", "محيط", "بحر", "نهر",
        "بحيرة", "جبل", "صحراء",
        "جليد", "قطب", "شمال", "جنوب",
        "حيوان", "نبات",
        "نوع", "انقراض", "مهدد",
        "محمية", "تنوع", "تنوع أحيائي",
        "أحيائي", "نظام", "إيكولوجي",
        "سلسلة", "غذائية",
        "طاقة", "متجددة", "طاقة متجددة",
        "شمس", "رياح", "نووي", "نووية",
        "أحفوري", "بترول", "غاز", "فحم",
        # Specific episodes (from actual data)
        "البيئة", "طبيعة",
        "تغير المناخ", "مناخ", "احتباس حراري",
        "الطاقة", "طاقة", "طاقة متجددة",
        "الموارد", "مورد", "المعادن", "معدن",
        "الوقود", "وقود", "النفط", "نفط",
        "الغاز", "غاز", "الفحم", "فحم",
        "الشمس", "شمس", "الرياح", "رياح",
        "النووية", "نووي", "إشعاع",
        "المياه", "ماء", "الهواء", "هواء",
        "التربة", "تربة", "الغابات", "غابة",
        "المحيطات", "محيط", "البحار", "بحر",
        "الأنهار", "نهر", "الجبال", "جبل",
        "الصحاري", "صحراء", "الحيوانات", "حيوان",
        "النباتات", "نبات", "الأنواع", "نوع",
        "الانقراض", "انقراض", "التنوع", "تنوع",
        "التهديد", "مهدد", "المحمية", "محمية",
        "النظم", "نظام", "نظام إيكولوجي",
        "كربون", "انبعاث كربون", "بصمة كربونية",
        "الطاقة المظلمة", "مادة مظلمة",
        # English keywords
        "environment", "environmental", "climate", "climate change",
        "global warming", "carbon", "carbon footprint", "carbon emission",
        "emission", "emissions", "pollution", "pollutant", "pollutants",
        "air quality", "water quality", "air pollution", "water pollution",
        "soil", "soil contamination", "forest", "forests", "deforestation",
        "ocean", "oceans", "oceanic", "marine", "marine life",
        "river", "rivers", "climate system", "weather",
        "greenhouse gas", "greenhouse", "CO2", "carbon dioxide",
        "methane", "methane emission", "renewable", "renewable energy",
        "solar", "wind power", "wind energy", "hydroelectric",
        "fossil fuel", "fossil fuels", "oil", "oil spill",
        "nuclear", "nuclear power", "radiation", "radioactive",
        "extinction", "endangered", "endangered species",
        "conservation", "conserve", "protected area",
        "ecosystem", "ecosystems", "biodiversity",
        "habitat", "habitats", "habitat loss", "species",
        "wildlife", "wild animals", "wild", "nature", "natural",
        "earth", "Earth", "planet", "global", "global ecosystem",
        "atmosphere", "hydrosphere", "lithosphere", "biosphere",
        "biome", "biomes", "ecology", "ecologist", "ecological",
        "environmental science", "dark energy", "dark matter",
    ],
    "دين وفكر": [
        "دين", "إسلام", "مسيحية", "يهودية",
        "بوذية", "هندوسية",
        "قرآن", "حديث", "سنة",
        "فقه", "أصول", "تفسير",
        "سيرة", "صحابة", "تابعين",
        "أئمة", "مذاهب",
        "شيعة", "صوفية", "سلفية",
        "إخوان", "كلام", "منطق",
        "فلسفة إسلامية",
        "فارابي", "ابن سينا", "غزالي",
        "ابن رشد", "ابن تيمية", "ابن خلدون",
        # Specific episodes
        "دين", "ديني", "دين",
        "إسلام", "مسلم", "مسلمة",
        "مسيحي", "مسيحية",
        "يهودي", "يهودية",
        "بوذي", "بوذية",
        "هندوسي", "هندوسية",
        "قرآن", "قرآني",
        "حديث", "حديثي",
        "سنة", "سنوي",
        "فقه", "فقهي",
        "أصول", "أصولي",
        "تفسير", "تفسيري",
        "سيرة", "سير",
        "صحابة", "صحابي",
        "تابعين", "تابعي",
        "أئمة", "إمام",
        "مذاهب", "مذهب",
        "شيعة", "شيعي",
        "صوفية", "صوفي",
        "سلفية", "سلفي",
        "إخوان", "إخواني",
        "كلام", "كلامي",
        "منطق", "منطقي",
        "فلاسفة", "فلاسفة",
        "علماء", "عالم",
        "أديان", "ديانة",
        "دينية", "ديني",
        # Specific episodes
        "100 مليون سنة أكل", "100 مليون",
        "الصيام", "صيام",
        "ليه بنتخن في رمضان؟", "رمضان",
        "خمر الصالحين", "خمر",
        "الصلاة", "صلاة",
        "الزكاة", "زكاة",
        "الحج", "حج",
        "الصيام", "صيام",
        "الصلاة", "صلاة",
        "الإيمان", "إيمان",
        "الكفر", "كفر",
        "المعصية", "معصية",
        "الطاعة", "طاعة",
        "العصاة", "عصاة",
        "الملحد", "ملحد",
        "الملحدة", "ملحدة",
        "الإله", "إله",
        "إله الشر", "الشيطان", "شيطان",
        "الشرير", "شرير",
        "النبوة", "نبي",
        "الرسل", "رسول",
        "الإنجيل", "إنجيل",
        "التوراة", "توراة",
        "الزبور", "زبور",
        "الأنبياء", "نبي",
        # English keywords
        "religion", "religious", "religious,",
        "Islam", "Muslim", "Islamic", "Quran", "Qur'an",
        "Hadith", "Sunnah", "Sunnah-based",
        "prophet", "prophets", "prophetic",
        "faith", "faith-based",
        "spiritual", "spirituality",
        "worship", "worshipping",
        "prayer", "prayers", "pray",
        "fasting", "fast", "Ramadan",
        "charity", "zakat", "almsgiving",
        "pilgrimage", "Hajj",
        "mosque", "church", "temple",
        "religious text", "sacred text",
        "theology", "theological",
        "theological seminary", "religious studies",
        "fellowship", "congregation",
        "imam", "priest", "rabbi", "monk",
        "clergy", "laity",
        "sect", "sectarian",
        "shia", "sunni", "shia'a",
        "sufi", "sufism",
        "crusade", "crusader", "crusades",
        "jihad", "jihadi", "mujahideen",
        "halal", "haram", "haram,",
        "ritual", "rituals",
        "ritual prayer",
        "sacred", "sacred text",
        "religious practice",
        "worship", "worship service",
        "Islamic history", "Islamic Golden Age",
        "philosophy of religion",
    ],
    "غريب وعجيب": [
        "غريب", "عجيب", "غيب",
        "خوارق", "أشباح", "جن",
        "سحر", "شعوذة", "عرافة",
        "كهانة", "طالع", "أبراج",
        "حظ", "قدر",
        "مصير", "نبوءة", "رؤيا",
        "حلم", "كابوس",
        "تخاطر", "تنويم",
        "مغناطيسي", "باراسايكولوجي",
        "يو إف أو", "كائنات",
        "فضائية", "مجهول",
        "مثلث برمودا", "أتلانتس",
        "لموريا", "هرم", "أهرامات",
        "ظواهر", "ظواهر",
        "خفيف", "ثقل",
        "طير", "يحلق",
        "طائر", "طائرات",
        "طيران", "طيران",
        "الطيران", "طيران",
        "جواد", "جياد",
        "البرية", "برية",
        "البحرية", "بحرية",
        "الجوية", "جوية",
        "الفضائية", "فضائية",
        "الفضاء", "فضاء",
        "السفينة", "سفينة",
        "الغوص", "غوص",
        "المحيط", "محيط",
        "البحر", "بحر",
        "النهر", "نهر",
        # Specific episodes
        "الجوكر", "جوكر",
        "سوبر هيروز", "هيروز",
        "فانتازيا", "خيال",
        "أسطورة", "أساطير",
        "خرافة", "خرافات",
        "أسطورة", "أساطير",
        "خرافة", "خرافات",
        "أساطير", "خرافات",
        "وهم", "أحلام",
        "كابوس", "كابوس",
        "رؤيا", "رؤية",
        "حلم", "أحلام",
        "تخاطر", "تخاطر",
        "سحر", "سحري",
        "شعوذة", "شعوذي",
        "خوارق", "خارق",
        "عجيب", "عجيب",
        "غريب", "غريب",
        "جن", "أشباح", "شبح",
        "كاهن", "كهانة",
        "عراف", "عرافة",
        "طالع", "طالعي",
        "أبراج", "برج",
        "حظ", "قدر",
        "مصير", "نبوءة",
        "مغناطيسي", "مغناطيس",
        "باراسايكولوجيا", "باراسايكولوجي",
        "UFO", "UFO", "UFO",
        "كائنات فضائية", "كائن فضائي",
        "مجهول", "مجهولات",
        "مثلث برمودا", "برمودا",
        "أتلانتس", "أتلانتس",
        "لموريا", "لموريا",
        "هرم", "هرم",
        "أهرامات", "أهرام",
        # English keywords
        "weird", "weird,", "weirdest",
        "strange", "strange,",
        "paranormal", "paranormal,",
        "supernatural", "supernatural,",
        "ghost", "ghosts", "ghost,",
        "haunted", "haunting",
        "spirit", "spirits", "spiritual",
        "psychic", "psychics",
        "medium", "mediums",
        "clairvoyant", "clairvoyance",
        "mystery", "mysterious",
        "mystery,", "mysterious,",
        "paranormal investigation",
        "UFO", "UFOs", "UFO,",
        "UFO sighting", "UFOs sightings",
        "alien", "aliens", "alien,",
        "extraterrestrial", "ET", "ETs",
        "cryptid", "cryptozoology",
        "cryptozoology",
        "conspiracy", "conspiracy theory",
        "conspiracy theory,",
        "secret", "secrets",
        "hidden", "hidden history",
        "occult", "occultist",
        "arcane", "arcane knowledge",
        "supernatural phenomena",
        "unexplained", "unexplained phenomena",
        "mysterious phenomenon",
        "Bermuda Triangle",
        "Bermuda Triangle,",
        "Atlantis", "Atlantis,",
        "Loch Ness", "Loch Ness Monster",
        "Yeti", "Abominable Snowman",
        "Bigfoot", "Sasquatch",
        "Chupacabra", "Chupacabra,",
        "phantom", "phantom",
        "ghostly", "ghost story",
    ],
    "عام / متنوع": [],
}


# Category ordering for display (affects which category wins on ties)
CATEGORY_ORDER = [
    "تاريخ",
    "علوم",
    "طب وصحة",
    "علم نفس واجتماع",
    "اقتصاد وأعمال",
    "فلسفة ومنطق",
    "لغة وآداب",
    "تقنية وذكاء اصطناعي",
    "فنون وإعلام",
    "بيئة وطبيعة",
    "دين وفكر",
    "غريب وعجيب",
    "عام / متنوع",
]


# ============ TITLE TOPIC EXTRACTION ============
# Patterns to strip the channel prefix/suffix from episode titles
TITLE_PREFIX_PATTERN = re.compile(r'^الدحيح\s*[\|\-–]\s*', re.IGNORECASE)
TITLE_SUFFIX_PATTERN = re.compile(r'\s*\|\s*الدحيح\s*$', re.IGNORECASE)

# Episode title formats observed:
# 1. "الدحيح | Descriptive Topic" (older, longer)
# 2. "الدحيح - Short Topic" (newer, shorter)
# 3. "Topic | الدحيح" (reversed)
# 4. "موسم جديد من الدحيح" / "ماذا قال الدحيح عن...؟" (meta Q&A)
# 5. "Topic" (no prefix/suffix)


def extract_topic(title: str) -> str:
    """
    Extract the core topic from an episode title by removing
    the 'الدحيح | / -' prefix and '| الدحيق' suffix.

    Returns the topic string, or the original title if no prefix/suffix found.
    """
    if not title:
        return ""

    topic = title.strip()

    # Strip prefix: "الدحيح | Topic" or "الدحيح - Topic" etc.
    topic = TITLE_PREFIX_PATTERN.sub('', topic).strip()

    # Strip suffix: "Topic | الدحيح"
    topic = TITLE_SUFFIX_PATTERN.sub('', topic).strip()

    return topic


def extract_arabic_text(text: str) -> str:
    """
    Extract only Arabic-script text from a mixed string.
    Helps filter out English references/URLs when matching Arabic keywords.
    """
    if not text:
        return ""
    # Arabic Unicode range: ؀-ۿ plus common supplements
    # Also include Arabic extended, presentation forms, etc.
    arabic_ranges = [
        '؀-ۿ',  # Arabic
        'ݐ-ݿ',  # Arabic Supplement
        'ࢠ-ࣿ',  # Arabic Extended-A
        'ﭐ-﷿',  # Arabic Presentation Forms-A
        'ﹰ-﻿',  # Arabic Presentation Forms-B
    ]
    pattern = '[' + '|'.join(arabic_ranges) + ']+'
    # Find all Arabic text segments
    matches = re.findall(pattern, text)
    return ' '.join(matches)


def extract_english_text(text: str) -> str:
    """
    Extract English words from a mixed string for keyword matching.
    Filters out URLs but keeps book titles, author names, etc.
    """
    if not text:
        return ""
    # Find English words (sequences of ASCII letters, possibly with spaces)
    matches = re.findall(r'[A-Za-z]+(?:\s+[A-Za-z]+)*', text)
    return ' '.join(matches)


# ============ TOPIC PATTERNS ============
# Specific topic patterns that map directly to categories.
# These match against the extracted topic from episode titles.
# Order matters: more specific patterns should come first.
TOPIC_PATTERNS: list[tuple[str, str, float, str]] = [
    # (arabic_pattern, category, confidence, description)
    # History / biography
    (r'أخناتون|آخناتون|آخناتون', "تاريخ", 0.90, "أخناتون الملك الفرعوني"),
    (r'روبين ويليامز|روبين ويليام', "تاريخ", 0.85, "روبين ويليامز ممثل/مؤلف"),
    (r'فلاديمير بوتين|بوتين', "تاريخ", 0.90, "فلاديمير بوتين الزعيم الروسي"),
    (r'دونالد ترامب|ترامب', "تاريخ", 0.90, "دونالد ترامب الرئيس الأمريكي"),
    (r'أنجيلا ميركل|ميركل', "تاريخ", 0.88, "أنجيلا ميركل المستشارة الألمانية"),
    (r'جون كينيدي|كينيدي', "تاريخ", 0.88, "جون كينيدي الرئيس الأمريكي"),
    (r'فلاديمير لينين|لينين', "تاريخ", 0.90, "فلاديمير لينين"),
    (r'نابليون|نابي', "تاريخ", 0.90, "نابليون بونابرت"),
    (r'سورغ', "تاريخ", 0.85, "ريتشارد سورغ الجاسوس"),
    (r'تيد كازينسكي|كازينسكي', "تاريخ", 0.85, "تيد كازينسكي"),
    (r'تشارلي شابلن|شابلن', "تاريخ", 0.85, "تشارلي شابلن"),
    (r'إيلون ماسك|ماسك', "تقنية وذكاء اصطناعي", 0.85, "إيلون ماسك/تيل كوريل"),
    (r'سام ألتمان|ألتمان', "تقنية وذكاء اصطناعي", 0.85, "سام ألتمان/إنفيديا"),
    (r'مايك تايسون|تايسون', "فنون وإعلام", 0.85, "مايك تايسون المحترف"),
    (r'مانشستر يونايتد|مانشستر', "فنون وإعلام", 0.85, "مانشستر يونايتد نادي كرة قدم"),
    (r'ميسي|نيمار|أبو نيمار', "فنون وإعلام", 0.85, "ميسي/نيمار لاعبي كرة قدم"),
    (r'كريستيانو رونالدو|رونالدو', "فنون وإعلام", 0.85, "كريستيانو رونالدو"),
    (r'هتلر|ستالين', "تاريخ", 0.90, "هتلر/ستالين في التاريخ"),
    # ... many more
    # Frequent title-only topics whose descriptions are reference lists.
    (r'الماسونية|تاريخ جهنم', "دين وفكر", 0.86, "موضوع ديني/فكري محدد"),
    (r'أجهزة عذراء|القفز للمستقبل', "تقنية وذكاء اصطناعي", 0.84, "موضوع تقني محدد"),
    (r'يا محاسن الصدف|الصدفة', "علوم", 0.82, "الصدفة والاحتمالات"),
    (r'كريستيانو رونالدو|رونالدو|ميسي|نيمار', "فنون وإعلام", 0.88, "لاعب كرة قدم"),
    (r'فوبيا', "طب وصحة", 0.86, "الخوف والرهاب"),
    # High-signal topics observed in the current episode corpus.
    (r'سؤال ب.? 64 دولار|محكمة تفتيش', "تاريخ", 0.88, "محاكمة تاريخية أمريكية"),
    (r'ملك الغابة|ظاهرة الكلب المستضعف|الكائن الطباخ', "علوم", 0.88, "سلوك الحيوان"),
    (r'الصمت التام|لازم تنام|النوم|مدمن نجاحات', "طب وصحة", 0.86, "النوم والصحة"),
    (r'التفاوض مع طفلك|طفلك|أسوأ أم|إخوات في الرضاعة', "علم نفس واجتماع", 0.86, "العلاقات والتربية"),
    (r'الرجل العنكبوت|النرجسية|الذكاء الغبي|في مدح الكسل|التكديس القهري', "علم نفس واجتماع", 0.86, "علم النفس والسلوك"),
    (r'كرة القدم الأمريكية|كرة القدم|الرياضيون الخارقون', "فنون وإعلام", 0.86, "الرياضة والإعلام"),
    (r'الرقاقة الخطيرة|أجهزة عذراء|الروبوت|روبوتي|أخلاق الروبوتات|الذكاء الاصطناعي', "تقنية وذكاء اصطناعي", 0.88, "التقنية والذكاء الاصطناعي"),
    (r'الحبة الزرقاء|كيف يتعلم الأطباء|الطب الجنائي|ليه بنموت|الموت', "طب وصحة", 0.84, "الطب والحياة"),
    (r'عملة الفيسبوك|الاستغلال حلال|البيت كوي.?ن|صعود اليمين', "اقتصاد وأعمال", 0.82, "الاقتصاد والسياسة العامة"),
    (r'اللانهائية|الإنتروبي|الثقب الأسود|الاحتباس|المصفوفة', "علوم", 0.86, "مفهوم علمي محدد"),
    (r'لعبة الديكتاتور|معضلة المساجين|معضلة الحمار|المفروض مرفوض', "فلسفة ومنطق", 0.82, "معضلة فلسفية أو منطقية"),
    (r'فين الفضائيين|الفضائيين|عفاريت|الحاسة السادسة|موت قزح', "غريب وعجيب", 0.82, "موضوع غريب أو غير مألوف"),
    (r'محاسن الصدف|الصدفة|كلما يقل يكثر', "رياضيات", 0.82, "الاحتمالات والأنماط"),
    (r'أخطر فركشة في التاريخ|مديرون أشرار|سؤال 64 دولار', "تاريخ", 0.84, "موضوع تاريخي"),
    (r'موزاليزا|كوبي رايت|أغنية|بص بصة|شنب وفستان', "فنون وإعلام", 0.80, "الفنون والإعلام"),
    (r'أبوك كل بالليل|بموت من الجوع|المفروض مرفوض', "طب وصحة", 0.80, "الغذاء والصحة"),
]


def match_topic_pattern(topic: str) -> Optional[tuple[str, float, str]]:
    """Match topic against specific patterns. Returns (category, confidence, rationale)."""
    topic_lower = topic.lower()
    topic_norm = normalize_arabic_text(topic).lower()

    for pattern, category, confidence, rationale in TOPIC_PATTERNS:
        if re.search(pattern, topic_lower) or re.search(pattern, topic_norm):
            return category, confidence, rationale

    return None


# ============ TAXONOMY CONFIG (custom/merged) ============
_ACTIVE_TAXONOMY: dict[str, list[str]] = DEFAULT_TAXONOMY


def get_taxonomy() -> dict[str, list[str]]:
    """Return the currently active taxonomy (default, or merged with a loaded config)."""
    return _ACTIVE_TAXONOMY


def load_taxonomy_config(path: Path) -> dict[str, list[str]]:
    """
    Load a custom taxonomy JSON config and merge it into DEFAULT_TAXONOMY.

    Expected format: {"category_name": ["keyword1", "keyword2", ...], ...}
    Existing categories get their keyword lists extended (deduped);
    new categories are added as-is. Mutates the module-level active taxonomy
    used by classify_deterministic() / get_taxonomy().
    """
    global _ACTIVE_TAXONOMY
    with open(path, encoding="utf-8") as f:
        custom = json.load(f)

    merged = {cat: list(kws) for cat, kws in DEFAULT_TAXONOMY.items()}
    for category, keywords in custom.items():
        if category in merged:
            merged[category] = list(dict.fromkeys(merged[category] + list(keywords)))
        else:
            merged[category] = list(keywords)

    _ACTIVE_TAXONOMY = merged
    print(f"  [OK] Loaded taxonomy config: {path} ({len(custom)} categories merged)")
    return _ACTIVE_TAXONOMY


# ============ DETERMINISTIC CLASSIFICATION (Pass 1) ============
PROMPT_VERSION = "v1"


@dataclass
class ClassificationResult:
    """Result of classifying a single episode (from either pass)."""
    primary_category: str
    secondary_categories: list[str] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    model: str = "deterministic"
    prompt_version: str = PROMPT_VERSION
    all_candidates: list = field(default_factory=list)


def classify_deterministic(text: str) -> ClassificationResult:
    """
    Classify combined title+description text using rules only (no API calls).

    Two internal passes:
    1. Specific proper-name/topic regex patterns (TOPIC_PATTERNS) -> high confidence
       when a known person/place/topic is directly named.
    2. Keyword frequency scoring across the active taxonomy -> confidence based on
       how dominant the winning category is over the runner-up.
    """
    text = text or ""
    text_norm = normalize_arabic_text(text)
    text_lower = text_norm.lower()

    # Pass 1a: specific named-topic patterns (proper names etc.)
    pattern_match = match_topic_pattern(text)
    if pattern_match:
        category, confidence, rationale = pattern_match
        return ClassificationResult(
            primary_category=category,
            secondary_categories=[],
            confidence=confidence,
            rationale=f"مطابقة نمط محدد: {rationale}",
            model="deterministic",
            prompt_version=PROMPT_VERSION,
            all_candidates=[(category, confidence)],
        )

    # Pass 1b: keyword frequency scoring
    taxonomy = get_taxonomy()
    scores: dict[str, int] = {}
    for category, keywords in taxonomy.items():
        if not keywords:
            continue
        count = 0
        for kw in keywords:
            kw_norm = normalize_arabic_text(kw).lower()
            if not kw_norm:
                continue
            count += text_lower.count(kw_norm)
        if count:
            scores[category] = count

    if not scores:
        return ClassificationResult(
            primary_category="عام / متنوع",
            secondary_categories=[],
            confidence=0.3,
            rationale="لم يتم العثور على كلمات مفتاحية مطابقة",
            model="deterministic",
            prompt_version=PROMPT_VERSION,
            all_candidates=[],
        )

    ranked = sorted(
        scores.items(),
        key=lambda kv: (-kv[1], CATEGORY_ORDER.index(kv[0]) if kv[0] in CATEGORY_ORDER else 999),
    )
    primary_category, primary_score = ranked[0]

    if len(ranked) > 1:
        second_score = ranked[1][1]
        dominance = (primary_score - second_score) / primary_score if primary_score else 0.0
        confidence = min(0.95, 0.45 + 0.35 * dominance + 0.02 * min(primary_score, 10))
    else:
        confidence = min(0.95, 0.55 + 0.03 * min(primary_score, 10))

    secondary = [cat for cat, _ in ranked[1:4]]

    return ClassificationResult(
        primary_category=primary_category,
        secondary_categories=secondary,
        confidence=round(confidence, 2),
        rationale=f"تصنيف بناءً على {primary_score} تطابق كلمات مفتاحية لفئة {primary_category}",
        model="deterministic",
        prompt_version=PROMPT_VERSION,
        all_candidates=ranked,
    )


def classify_episode_deterministic(episode: Episode) -> ClassificationResult:
    """Classify an episode using its title topic before its description.

    Reference-heavy descriptions often contain no usable prose, while the title
    remains a reliable signal. Only a non-generic title result is allowed to
    override the combined-text result.
    """
    topic = extract_topic(episode.title)
    if topic:
        pattern_match = match_topic_pattern(topic)
        if pattern_match:
            category, confidence, rationale = pattern_match
            return ClassificationResult(
                primary_category=category,
                secondary_categories=[],
                confidence=confidence,
                rationale=f"مطابقة موضوع العنوان: {rationale}",
                model="deterministic-title",
                prompt_version=PROMPT_VERSION,
                all_candidates=[(category, confidence)],
            )

        title_result = classify_deterministic(topic)
        if title_result.primary_category != "عام / متنوع" and title_result.confidence >= 0.55:
            title_result.rationale = f"تصنيف من موضوع العنوان: {title_result.rationale}"
            title_result.model = "deterministic-title"
            return title_result

    combined = " ".join(part for part in (topic, episode.description) if part).strip()
    result = classify_deterministic(combined)
    if not episode.description.strip() and result.primary_category == "عام / متنوع":
        result.rationale = "لا توجد أوصاف قابلة للتصنيف؛ استُخدم العنوان دون تطابق موضوعي"
        result.confidence = 0.2
    return result


# ============ AI CLASSIFICATION (Pass 2 - fallback) ============
class AIProvider(str, Enum):
    """Supported AI providers for the pass-2 fallback classifier."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


_DEFAULT_MODELS = {
    AIProvider.OPENAI: "gpt-4o-mini",
    AIProvider.ANTHROPIC: "claude-haiku-4-5",
    AIProvider.GOOGLE: "gemini-1.5-flash",
}


class TwoPassClassifier:
    """
    Two-pass episode classifier:
      Pass 1: classify_deterministic() — free, instant, rule-based.
      Pass 2: only triggered when pass-1 confidence < confidence_threshold —
              calls the configured AI provider and, on a valid response,
              replaces the pass-1 result.

    Usage:
        clf = TwoPassClassifier(AIProvider.ANTHROPIC, api_key, "claude-haiku-4-5", 0.7)
        clf.classify(episode)   # mutates episode's classification_* fields in place
    """

    def __init__(
        self,
        ai_provider: AIProvider,
        ai_api_key: str,
        ai_model: str = "",
        confidence_threshold: float = 0.7,
    ):
        self.ai_provider = ai_provider
        self.ai_api_key = ai_api_key
        self.ai_model = ai_model or _DEFAULT_MODELS[ai_provider]
        self.confidence_threshold = confidence_threshold
        self._client: Any = None  # typed Any: holds whichever SDK's client object gets built lazily
        self._ai_failures = 0

    def classify(self, episode) -> ClassificationResult:
        """Classify an episode and write results directly onto its fields."""
        result = classify_episode_deterministic(episode)

        if result.confidence < self.confidence_threshold:
            ai_result = self._classify_with_ai(episode)
            if ai_result is not None:
                result = ai_result

        episode.primary_category = result.primary_category
        episode.secondary_categories = result.secondary_categories
        episode.classification_confidence = result.confidence
        episode.classification_rationale = result.rationale
        episode.classification_model = result.model
        episode.classification_prompt_version = result.prompt_version
        episode.classified_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        # all_candidates is a list of (category, score) tuples; Episode.proposed_categories
        # is typed list[str] and to_dict() does "|".join(...) on it directly, so tuples
        # would crash there the same way raw strings crashed on audit_status.value below.
        episode.proposed_categories = [f"{cat}:{score}" for cat, score in result.all_candidates]

        if result.confidence >= 0.8:
            episode.audit_status = AuditStatus.AUTO_HIGH
        elif result.confidence >= 0.5:
            episode.audit_status = AuditStatus.AUTO_MEDIUM
        else:
            episode.audit_status = AuditStatus.AUTO_LOW

        return result

    def _classify_with_ai(self, episode) -> Optional[ClassificationResult]:
        categories = list(get_taxonomy().keys())
        prompt = self._build_prompt(episode, categories)
        try:
            if self.ai_provider == AIProvider.ANTHROPIC:
                raw = self._call_anthropic(prompt)
            elif self.ai_provider == AIProvider.OPENAI:
                raw = self._call_openai(prompt)
            elif self.ai_provider == AIProvider.GOOGLE:
                raw = self._call_google(prompt)
            else:
                return None
        except Exception as e:
            self._ai_failures += 1
            print(f"  [WARN] AI classification failed for '{episode.title[:40]}...': {e}")
            return None

        return self._parse_ai_response(raw, categories)

    def _build_prompt(self, episode, categories: list[str]) -> str:
        cats = "، ".join(categories)
        desc = (episode.description or "")[:400]
        return (
            "صنّف الحلقة التالية إلى فئة واحدة فقط من هذه الفئات، ولا تستخدم أي فئة أخرى:\n"
            f"{cats}\n\n"
            f"العنوان: {episode.title}\n"
            f"الوصف: {desc}\n\n"
            "أجب بصيغة JSON فقط، بدون أي نص أو شرح خارج الـ JSON، بهذا الشكل بالضبط:\n"
            '{"primary_category": "...", "secondary_categories": ["..."], '
            '"confidence": 0.0, "rationale": "..."}'
        )

    def _call_anthropic(self, prompt: str) -> str:
        import anthropic
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.ai_api_key)
        response = self._client.messages.create(
            model=self.ai_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        # response.content is a list of blocks (TextBlock, ThinkingBlock, ToolUseBlock, ...);
        # only TextBlock has .text, so find the first text block instead of assuming content[0] is one.
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return ""

    def _call_openai(self, prompt: str) -> str:
        import openai
        if self._client is None:
            self._client = openai.OpenAI(api_key=self.ai_api_key)
        response = self._client.chat.completions.create(
            model=self.ai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        # .content is typed Optional[str] (can be None for refusals/tool calls) — the return
        # type here is `str`, so normalize None to "" rather than letting it leak through.
        return response.choices[0].message.content or ""

    def _call_google(self, prompt: str) -> str:
        import google.generativeai as genai
        # Pylance/Pyright can't see `configure`/`GenerativeModel` in current type stubs for
        # google-generativeai (they're exposed via the package's __getattr__ at runtime, not
        # as static top-level exports) — these calls work fine, the squiggles are stub gaps.
        genai.configure(api_key=self.ai_api_key)  # type: ignore[attr-defined]
        model = genai.GenerativeModel(self.ai_model)  # type: ignore[attr-defined]
        response = model.generate_content(prompt)
        return response.text or ""

    def _parse_ai_response(self, raw: str, categories: list[str]) -> Optional[ClassificationResult]:
        cleaned = (raw or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(json)?", "", cleaned).rstrip("`").strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

        primary = data.get("primary_category", "")
        if primary not in categories:
            return None

        confidence = float(data.get("confidence", 0.75))
        secondary = [c for c in data.get("secondary_categories", []) if c in categories and c != primary]

        return ClassificationResult(
            primary_category=primary,
            secondary_categories=secondary,
            confidence=confidence,
            rationale=data.get("rationale", ""),
            model=f"{self.ai_provider.value}:{self.ai_model}",
            prompt_version=PROMPT_VERSION,
            all_candidates=[(primary, confidence)],
        )
