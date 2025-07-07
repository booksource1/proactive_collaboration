
import os
import pprint
import sys

# Add the directory containing 'ultilities.py' to the sys.path
script_dir = os.path.dirname(
    os.path.abspath(__file__)
)  # Get the current script's directory
module_dir = os.path.join(
    script_dir, "robot_skill_sets"
)  # The folder where 'ultilities.py' is located
sys.path.append(module_dir)

from llm import completion
from prompts import misplaced_detect_prompt
from robot_skill_sets.ultilities import (
    relation_to_str,
)


def check_relation(relations):
    res = {}
    object_count = len(relations)
    rule_success = len(relations)
    LLM_success = len(relations)

    rule_misplaced = []
    for object in relations.keys():
        if relations[object]['on']:
            for on_obj in relations[object]['on']:
                if 'loor' in on_obj:
                    rule_misplaced.append(object.lower())

    res["misplaced_objects"] = list(relations.keys())

    new_observation = {}
    for key in relations.keys():
        new_observation[key] = {
            # "room": default_room,  # Replace with dynamic assignment if available
            "description": relation_to_str([key], {key: relations[key]})
        }

    obs_str = ""
    for obj, info in new_observation.items():
        description = info["description"]
        obs_str += f"{obj} - {description}\n"
    prompt = misplaced_detect_prompt.format(
        obj_and_description=obs_str,
    )

    response = completion(prompt)["response"]
    from tools import parse_json_from_response, get_closest_match
    
    misplaced_obj = parse_json_from_response(response, "misplaced_object")
    if isinstance(misplaced_obj, str):
        if "none" in misplaced_obj.lower():
            misplaced_obj = []
        else:
            misplaced_obj = [misplaced_obj]

    llm_misplaced = []
    if len(misplaced_obj) > 0:
        res['llm_success'] = False
        for obj in misplaced_obj:
            obj = get_closest_match(obj, relations.keys())
            if obj in relations.keys():
                llm_misplaced.append(obj.lower())
                LLM_success -= 1
        res['llm_misplaced_objects'] = llm_misplaced
    else:
        res['llm_success'] = True
        res['llm_misplaced_objects'] = []
    
    if rule_misplaced:
        res['rule_success'] = False
        res['rule_misplaced_object'] = rule_misplaced
        rule_success -= len(rule_misplaced)
    else:
        res['rule_success'] = True
        res['rule_misplaced_object'] = []

    success_flag = res['llm_success'] and res['rule_success']
    res['all_misplaced_objects'] = list(set(res['llm_misplaced_objects']) & set(res['rule_misplaced_object']))
    all_misplaced_count = len(res['all_misplaced_objects'])
    all_success_count = object_count - all_misplaced_count
    
    return success_flag, rule_success/object_count, LLM_success/object_count, all_success_count/object_count, res

    
if __name__ == "__main__":
    relations= {
    "Bread_01": {
    "on": [
        "CounterTop_02"
    ],
    "between": [
        [
        "Sink_02",
        "Walls"
        ]
    ]
    },
    "Newspaper_01": {
    "on": [
        "SideTable_01"
    ],
    "between": [
        [
        "ArmChair_01",
        "HousePlant_01"
        ]
    ]
    },
    "HousePlant_01": {
    "on": [
        "SideTable_01"
    ],
    "between": []
    },
    "Pillow_02": {
    "on": [
        "Floor_01"
    ],
    "between": []
    },
    "AlarmClock_01": {
    "on": [
        "Bed_01"
    ],
    "between": []
        }
    }
  
    
    pprint.pprint(check_relation(relations))