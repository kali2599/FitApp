import datetime as dt


ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

INTENSITIES = {
    "low": "low intensity",
    "moderate": "moderate intensity",
    "high": "high intensity",
}

STRESS_SUGGESTIONS = {
    "low": ("Recovery looks good", "Your reported stress is low, which supports consistent training and sleep."),
    "moderate": ("Watch your recovery", "Moderate stress can build up. Add a deload week or an extra rest day when it feels heavy."),
    "high": ("Prioritise recovery", "High stress raises cortisol and slows progress. Cut training volume, sleep more and keep meals regular."),
}

DIRECTION_LABELS = {
    "lose": "weight loss",
    "maintain": "maintenance",
    "gain": "muscle gain",
}


def _age(birth_date):
    if not birth_date:
        return None
    try:
        born = dt.date.fromisoformat(str(birth_date))
    except ValueError:
        return None
    today = dt.date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _round(value, digits=1):
    if value is None:
        return None
    return round(value, digits)


def bmi_category(bmi):
    if bmi is None:
        return None
    if bmi < 18.5:
        return "underweight"
    if bmi < 25:
        return "normal"
    if bmi < 30:
        return "overweight"
    return "obese"


def body_fat_category(sex, pct):
    if pct is None:
        return None
    if sex == "female":
        if pct < 14:
            return "essential fat"
        if pct < 22:
            return "athletic"
        if pct < 32:
            return "fitness"
        if pct < 40:
            return "average"
        return "obese"
    if pct < 5:
        return "essential fat"
    if pct < 13:
        return "athletic"
    if pct < 18:
        return "fitness"
    if pct < 25:
        return "average"
    return "obese"


def compute(user, stat, lifestyle=None):
    if user is None:
        return {"metrics": {}, "suggestions": []}

    lifestyle = dict(lifestyle) if lifestyle else {}
    height_cm = user["height_cm"]
    birth_date = user["birth_date"]
    sex = user["sex"] or ""
    weight_kg = stat["weight_kg"] if stat else None
    age = _age(birth_date)

    metrics = {}
    suggestions = []

    height_m = height_cm / 100.0 if height_cm else None
    if weight_kg and height_m:
        bmi = weight_kg / (height_m ** 2)
        metrics["bmi"] = _round(bmi)
        metrics["bmi_category"] = bmi_category(bmi)
        metrics["healthy_min"] = _round(18.5 * height_m ** 2)
        metrics["healthy_max"] = _round(24.9 * height_m ** 2)
    else:
        suggestions.append(
            {
                "tone": "info",
                "icon": "bi-rulers",
                "title": "Add your height and weight",
                "text": "We need a height in your profile and a recent weight measurement to calculate BMI and your calorie needs.",
            }
        )

    if age is None:
        suggestions.append(
            {
                "tone": "info",
                "icon": "bi-calendar-event",
                "title": "Add your birth date",
                "text": "Your age is used to estimate resting energy needs (BMR and calorie targets).",
            }
        )

    if weight_kg and height_m and age is not None:
        if sex == "male":
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
        elif sex == "female":
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
        else:
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 78
        metrics["bmr"] = _round(bmr)

        factor = ACTIVITY_FACTORS.get(lifestyle.get("activity_level") or "sedentary", 1.2)
        tdee = bmr * factor
        metrics["tdee"] = _round(tdee)

        direction = lifestyle.get("goal_direction") or "maintain"
        if direction == "lose":
            target = tdee * 0.825
        elif direction == "gain":
            target = tdee * 1.125
        else:
            target = tdee
        metrics["calorie_target"] = _round(target)
        metrics["goal_direction"] = direction

        protein_per_kg = 2.0 if direction == "lose" else 1.7
        metrics["protein_g"] = round(weight_kg * protein_per_kg)
        metrics["fat_g"] = round(target * 0.25 / 9)
        metrics["carbs_g"] = round((target - weight_kg * protein_per_kg * 4 - target * 0.25) / 4)

        if lifestyle.get("daily_calories"):
            intake = lifestyle["daily_calories"]
            delta = intake - target
            metrics["calorie_delta"] = _round(delta, 0)
            if direction == "lose" and delta > 0:
                suggestions.append(
                    {
                        "tone": "warning",
                        "icon": "bi-egg-fried",
                        "title": f"Eat about {_round(delta, 0)} less per day",
                        "text": f"Your logged intake ({_round(intake, 0)} kcal) exceeds the {_round(target, 0)} kcal needed to lose weight. A deficit of ~450 kcal/week drops roughly 0.5 kg of fat.",
                    }
                )
            elif direction == "gain" and delta < 0:
                suggestions.append(
                    {
                        "tone": "warning",
                        "icon": "bi-egg-fried",
                        "title": f"Add about {_round(-delta, 0)} kcal per day",
                        "text": f"Your intake ({_round(intake, 0)} kcal) is below the {_round(target, 0)} kcal target for muscle gain. Add an extra snack or a larger portion.",
                    }
                )
            else:
                suggestions.append(
                    {
                        "tone": "success",
                        "icon": "bi-check2-circle",
                        "title": "Calories look on track",
                        "text": f"Intake of {_round(intake, 0)} kcal/day matches the {_round(target, 0)} kcal target for {DIRECTION_LABELS[direction]}.",
                    }
                )
        else:
            suggestions.append(
                {
                    "tone": "info",
                    "icon": "bi-calculator",
                    "title": f"Aim for ~{_round(target, 0)} kcal/day",
                    "text": f"Your estimated maintenance is ~{_round(tdee, 0)} kcal/day. For {DIRECTION_LABELS[direction]}, target ~{_round(target, 0)} kcal and set protein at ~{metrics['protein_g']} g/day.",
                }
            )

        if direction == "lose":
            suggestions.append(
                {
                    "tone": "info",
                    "icon": "bi-file-earmark-bar-graph",
                    "title": "Keep protein high while cutting",
                    "text": f"Aim for ~{metrics['protein_g']} g protein, ~{metrics['fat_g']} g fat and ~{metrics['carbs_g']} g carbs per day to protect muscle while losing fat.",
                }
            )
    else:
        if weight_kg and height_m:
            suggestions.append(
                {
                    "tone": "info",
                    "icon": "bi-person-line",
                    "title": "Add your birth date",
                    "text": "Without your age we cannot estimate BMR, calorie targets or macros.",
                }
            )

    if stat and (stat["body_fat_pct"] is not None):
        metrics["body_fat_category"] = body_fat_category(sex, stat["body_fat_pct"])
        suggestions.append(
            {
                "tone": "info",
                "icon": "bi-percent",
                "title": f"Body fat: {metrics['body_fat_category']}",
                "text": f"At {_round(stat['body_fat_pct'])}%, resistance training plus a small calorie surplus builds lean mass; a deficit (with high protein) trims fat.",
            }
        )

    if stat and stat["waist_cm"] and height_cm:
        ratio = stat["waist_cm"] / height_cm
        metrics["whr"] = _round(ratio)
        if ratio < 0.5:
            suggestions.append(
                {
                    "tone": "success",
                    "icon": "bi-heart-pulse",
                    "title": "Healthy waist-to-height ratio",
                    "text": f"A ratio of {_round(ratio)} (< 0.5) is linked with lower cardio-metabolic risk. Keep it there.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "warning",
                    "icon": "bi-heart-pulse",
                    "title": "Trim your waist measurement",
                    "text": f"A waist-to-height ratio of {_round(ratio)} (≥ 0.5) raises cardio-metabolic risk. A small calorie deficit plus core work will bring it down.",
                }
            )

    sessions = lifestyle.get("sessions_per_week")
    if sessions is not None:
        if sessions < 2:
            suggestions.append(
                {
                    "tone": "warning",
                    "icon": "bi-activity",
                    "title": "Train at least twice a week",
                    "text": f"You train ~{sessions}x/week. Aim for 2-3 full-body sessions to build a solid training base.",
                }
            )
        elif sessions > 5:
            suggestions.append(
                {
                    "tone": "warning",
                    "icon": "bi-arrow-repeat",
                    "title": "Leave a rest day",
                    "text": f"{sessions} sessions a week is a lot. Schedule at least one full rest day and sleep well to recover.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "success",
                    "icon": "bi-check2-circle",
                    "title": "Good training frequency",
                    "text": f"{sessions}x/week is a solid frequency for consistent progress.",
                }
            )

    duration = lifestyle.get("session_duration_min")
    intensity = lifestyle.get("intensity")
    if sessions and duration:
        volume = sessions * duration
        if volume < 90:
            suggestions.append(
                {
                    "tone": "warning",
                    "icon": "bi-clock-history",
                    "title": "Build your weekly volume",
                    "text": f"~{volume} min/week of training is light. Raising it to 150+ minutes delivers clearer changes in body composition.",
                }
            )
        elif volume >= 300:
            suggestions.append(
                {
                    "tone": "success",
                    "icon": "bi-lightning-charge",
                    "title": "Solid training volume",
                    "text": f"~{volume} min/week keeps your {INTENSITIES.get(intensity, 'training') or 'training'} sessions effective.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "info",
                    "icon": "bi-graph-up-arrow",
                    "title": "You are on the right path",
                    "text": f"~{volume} min/week is good. Add 10% more volume only every 2-3 weeks to progress safely.",
                }
            )

    sleep = lifestyle.get("sleep_hours")
    if sleep is not None:
        metrics["sleep_hours"] = sleep
        if sleep < 7:
            suggestions.append(
                {
                    "tone": "warning",
                    "icon": "bi-moon-stars",
                    "title": "Sleep a bit more",
                    "text": f"~{sleep:g} h is below the 7-9 h that muscle recovery and appetite regulation need. Aim for 7+ h on training days.",
                }
            )
        elif sleep > 9:
            suggestions.append(
                {
                    "tone": "info",
                    "icon": "bi-moon",
                    "title": "Sleep amount is high",
                    "text": f"{sleep:g} h is fine occasionally, but very long nights can also mask low sleep quality. Keep a consistent wake time.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "success",
                    "icon": "bi-check2-circle",
                    "title": "Good sleep",
                    "text": f"{sleep:g} h supports recovery and helps keep cravings in check.",
                }
            )

    water = lifestyle.get("water_cups")
    if water is not None and weight_kg:
        target_cups = weight_kg * 0.035 / 0.24
        metrics["water_target_cups"] = _round(target_cups, 0)
        if water < target_cups:
            suggestions.append(
                {
                    "tone": "info",
                    "icon": "bi-droplet-half",
                    "title": "Drink more water",
                    "text": f"At ~{_round(water)} cups/day you are below the ~{metrics['water_target_cups']} cups suggested for your body weight.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "success",
                    "icon": "bi-droplet-half",
                    "title": "Good hydration",
                    "text": f"~{_round(water)} cups/day covers your needs well.",
                }
            )

    stress = lifestyle.get("stress_level")
    if stress:
        title, text = STRESS_SUGGESTIONS[stress]
        suggestions.append({"tone": "info", "icon": "bi-flower1", "title": title, "text": text})

    if not lifestyle and stat is None:
        suggestions.append(
            {
                "tone": "info",
                "icon": "bi-lightbulb",
                "title": "Complete your lifestyle profile",
                "text": "Answer a few questions about training, sleep and nutrition to get personalised suggestions.",
            }
        )

    return {"metrics": metrics, "suggestions": suggestions}