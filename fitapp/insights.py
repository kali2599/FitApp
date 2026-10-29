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
    "low": ("Reported stress", "You reported low stress. This is a profile summary, not an assessment of recovery."),
    "moderate": ("Reported stress", "You reported moderate stress. Consider how your current routine feels alongside this self-reported rating."),
    "high": ("Review your recovery", "You reported high stress. Consider whether your current training load and recovery routines feel manageable."),
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
        metrics["carbs_g"] = max(0, round((target - weight_kg * protein_per_kg * 4 - target * 0.25) / 4))

        suggestions.append(
            {
                "tone": "info",
                "icon": "bi-calculator",
                "title": f"Estimated starting point: ~{_round(target, 0)} kcal/day",
                "text": f"This rough estimate uses your profile, an activity multiplier, and a {DIRECTION_LABELS[direction]} adjustment. It is not measured intake or a personalised prescription.",
            }
        )

        if direction == "lose":
            suggestions.append(
                {
                    "tone": "info",
                    "icon": "bi-file-earmark-bar-graph",
                    "title": "Example macro split",
                    "text": f"The app's simple estimate uses ~{metrics['protein_g']} g protein, ~{metrics['fat_g']} g fat and ~{metrics['carbs_g']} g carbohydrates. Adjust these to your needs and preferences.",
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
                "text": "Body-fat estimates depend on the measurement method and are best viewed as a trend over time.",
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
                    "title": "Waist-to-height ratio",
                    "text": f"Your ratio is {_round(ratio)}. The 0.5 threshold is a broad screening reference, not a diagnosis.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "warning",
                    "icon": "bi-heart-pulse",
                    "title": "Waist-to-height ratio",
                    "text": f"Your ratio is {_round(ratio)}. Values around or above 0.5 are sometimes used as a screening prompt; this is not a diagnosis or a specific training prescription.",
                }
            )

    sessions = lifestyle.get("sessions_per_week")
    if sessions is not None:
        if sessions < 2:
            suggestions.append(
                {
                    "tone": "warning",
                    "icon": "bi-activity",
                    "title": "Training frequency",
                    "text": f"You reported about {sessions} sessions per week. This is context for your profile; choose a schedule that suits your goals and recovery.",
                }
            )
        elif sessions > 5:
            suggestions.append(
                {
                    "tone": "warning",
                    "icon": "bi-arrow-repeat",
                    "title": "Training frequency",
                    "text": f"You reported {sessions} sessions per week. Consider how your energy and recovery feel at this frequency.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "success",
                    "icon": "bi-check2-circle",
                    "title": "Training frequency",
                    "text": f"You reported {sessions} sessions per week. Training frequency is one part of your overall routine.",
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
                    "title": "Reported weekly training time",
                    "text": f"Your profile adds up to about {volume} minutes per week. This is descriptive context, not a measure of training quality or a target.",
                }
            )
        elif volume >= 300:
            suggestions.append(
                {
                    "tone": "success",
                    "icon": "bi-lightning-charge",
                    "title": "Reported weekly training time",
                    "text": f"Your profile adds up to about {volume} minutes per week at {INTENSITIES.get(intensity, 'unspecified intensity')}. This estimate does not assess workout quality.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "info",
                    "icon": "bi-graph-up-arrow",
                    "title": "Reported weekly training time",
                    "text": f"Your profile adds up to about {volume} minutes per week. Use this as a summary of your input, not a prescribed progression.",
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
                    "title": "Sleep duration",
                    "text": f"You reported about {sleep:g} hours per night. Sleep needs vary; consider this alongside how rested you feel.",
                }
            )
        elif sleep > 9:
            suggestions.append(
                {
                    "tone": "info",
                    "icon": "bi-moon",
                    "title": "Sleep duration",
                    "text": f"You reported about {sleep:g} hours per night. The app cannot assess sleep quality from duration alone.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "success",
                    "icon": "bi-check2-circle",
                    "title": "Sleep duration",
                    "text": f"You reported about {sleep:g} hours per night. This is a profile summary, not an assessment of sleep quality.",
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
                    "title": "Water intake",
                    "text": f"You reported about {_round(water)} cups per day. Hydration needs vary with climate, activity, diet, and health.",
                }
            )
        else:
            suggestions.append(
                {
                    "tone": "success",
                    "icon": "bi-droplet-half",
                    "title": "Water intake",
                    "text": f"You reported about {_round(water)} cups per day. The app cannot determine hydration needs from weight alone.",
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

    return {
        "metrics": metrics,
        "suggestions": suggestions,
        "disclaimer": "These are rough estimates, not measurements or medical advice. BMI does not distinguish muscle from fat. Energy estimates use a formula, your profile details, and an activity multiplier (sedentary when unset); lose/gain targets apply fixed adjustments of 17.5%/12.5%. Macro estimates use a simple split. Individual needs vary.",
    }
