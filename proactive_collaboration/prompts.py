current_state = """
- Current Time Step: {step}
- Your Unique Capacity: {capacity}
- Teammates: {teammates}
- Task Progress: {progress}
- Your SubTask: {subtask}
- Current Location: {location}
- Current Observation: {observation}
- Action History: {action}
"""

# - When there are no specific subtasks to execute, division exploration environment, one robot per room is a good choice.
communication_plan_prompt = """You are {robot_name}, a member of a heterogeneous robot team focused on efficiently exploring all known rooms and completing the repositioning tasks outlined in the task progress.

Your goal is to create a communication plan that aligns with the communication objective {goal} and the newly recept mesage in this **communication step**. 

Consider the following aspects and include them in your plan only if they are relevant:

1. **Information Synchronization**: 
    - Report newly discovered misplaced objects or changes in task status.
    - Inform teammates about successful actions that enable the next steps (e.g., reaching a destination to collaboratively pull a bed).

2. **Task Assignment**:
    - Volunteer for new or unassigned tasks.
    - Assign tasks to teammates to improve efficiency.

3. **Requesting Assistance**:
    - Seek help when facing obstacles beyond your capabilities (e.g., insufficient strength to move heavy objects).
    - Request assistance when discovering misplaced objects that are not part of your current tasks.

4. **Requesting New Member from Robot Pool**:
    - Request additional team members or specific capabilities when current resources are insufficient or when doing so can enhance overall efficiency.
    - Seek extra members to improve efficiency in managing newly discovered but currently unaddressed targets.

5. **Offer Help**:
    - When you are idle or engaged in exploratory tasks, proactively offer your help to team members to enhance overall efficiency and support team objectives.
    - Upon joining the team, assist requesters by addressing unhandled misplaced objects or by consolidating pulled objects.


Use the following format and guidelines to structure your communication plan:

### Subtask Format ###
- [replace] <object> <target_position>  # For small objects like apple, pillow, etc.
- [explore] <room_name>
- [gopull] <object>  # For large furniture like bed, sofa, etc.

    
### Inputs ###
=== Current Status ===
{current_status}

=== Robot Pool ===
Robot Pool have several robots, if you and your teammates can't handle the task or need to improve task effeciency you can send [request_new_member] your request number and capability of the new member you need.

=== Task Progress ===
{task_progress}

=== Last Subtask ===
{current_subtask}

=== Action History ===
{action_history}

=== Dialogue History ===
{dialogue_history}

### Response Format ###
<Thinking>
Step-by-step reasoning about the communication plan.

<Communication Plan>
response in a json format:
```json
{{
    "facts": ["The facts about the communication goal"],  
    "plan": [["plan_type", "The detailed communication plans to achieve the goal"]]
}}
```

Note:
1) When handling a replacement task, complete it independently if possible. Don't take two or more replacement tasks at the same time. Assign tasks to teammates to improve efficiency.
2) Always prioritize replacing any misplaced objects in your current room by relocating them to the nearest appropriate position—preferably within the same room—before considering any other tasks.
3) Take action to complete the replacement task as quickly as possible. Do not wait for teammates to act unless collaborating to move heavy objects.
4) You can only explore rooms: {all_rooms}; only do subtask in shown in **task progress**.
5) Try to take different tasks with your teammates unless pull heavy object together. [replace] can be done independently.
6) Take a not complete task when you have time and no other task to do. Piroty replacement task, when no replacement subtask do explore.
7) You can request new member to handle replacement subtask if all robots are busy.
"""

communication_prompt = """You are {robot_name}, a member of a heterogeneous robot team focused on efficiently exploring all known rooms and completing the repositioning tasks outlined in the task progress.

Your goal is to efficiently reposition misplaced objects to their appropriate places. Based on the current state, task progress, dialogue history, communication goal and facts, decide on the communication message to be sent to your teammates.

### Subtask Format ###
- [replace] <object> <target_position>  # object can be pick and place is small object, like apple, pillow, etc.
- [explore] <room_name>
- [gopull] <object>  # object can pull is big furniture, like bed, sofa, etc.


### Provided Inputs ###
=== Current Status ===
{current_status}

=== Robot Pool ===
The Robot Pool has several robots available. If you and your teammates are unable to handle the task, you can use [request_new_member] to specify the request number and the required capabilities of the new member.

=== Task Progress ===
{task_progress}

=== Last Subtask ===
{current_subtask}

=== Action History ===
{action_history}

=== Dialogue History ===
{dialogue_history}

=== Communication Plan ===
{communication_goal}

=== Facts of the Communication Plan ===
{facts}

### Response Format ###
<Thinking>
Step-by-step reasoning: 
1. Analyze the current task status, task progress, and dialogue history.
2. Determine the necessary communication based on the communication goal and facts.
3. Decide on the message to be sent to your teammates.
    - What information should I send to which robot?
    - If request other robot's help, tell the collaborator that you have already contacted the robot to avoid duplicate requests at same time.
    - If request new member from Robot Pool, inform your teammates that help has already been sought to prevent redundant requests at same time.

<Communication Message>
```json
{{
    "necessity": "Consider the necessity of sending a message",
    "contents": [
        {{
            "receiver": ["list of receiver's name or ["everyone"] if broadcasting the message, "None" if keeping silent, "[request_new_member]" if request new member from robot pool],
            "message": "brief message content to be sent to receiver", "None" if keeping silent"
        }},
        ...
    ]
}}
```

Notes: 
1) When handling a replacement task, complete it **independently** if possible. Don't take two or more replacement tasks at the same time. Assign tasks to teammates to improve efficiency.
2) Priority replacement task, when no replacement subtask do explore.
3) You can only explore rooms: {all_rooms}; only do subtask in shown in **task progress**.
4) Do not need to ask other robot's for observation because they will active to tell you if they have new observation.
5) If you are only sharing your task or observations and do not require a response, explicitly state that this message does not need a reply.
6) Take a not complete task when you have time and no other task to do. You can offer help when you are idle or take a explore task.
7) Priority pull task then replacement task, when no replacement subtask do explore.
8) You can request new member to handle replacement subtask if all robots are busy.
9) **AVOID repeating send similar message**. Be concise and **avoid unnecessary politeness**. Send to "everyone" cautiously as it consumes significant communication bandwidth..
"""

communication_goal_update_prompt = """You are {robot_name}, a member of a heterogeneous robot team focused on efficiently exploring all known rooms and completing the repositioning tasks outlined in the task progress.

Your goal is to assess the progress and content of the communication plan by updating it, along with the fact base, based on the communication objectives and the latest information obtained from teammates during the dialogue.

Use the following format and guidelines to update communication plan:

### Subtask Format ###
- [replace] <object> <target_position>  # For small objects like apple, pillow, etc.
- [explore] <room_name>
- [gopull] <object>  # For large furniture like bed, sofa, etc.


### Plan Type ### 
1. **Information Synchronization**
2. **Task Assignment**
3. **Requesting Assistance**
4. **Requesting New Member from Robot Pool**
5. **Offer Help**

### Plan Status ###
- In progress: The plan is not complete
- Complete:
    - Information Synchronization complete if you tell this information to related robot.
    - Task Assignment complete if you confirm your task or send message to assign task to other robot.
    - Requesting Assistance complete if you send message to request help and other robot confirm to help.
    - Requesting New Member from Robot Pool complete if you send message to request new member from Robot Pool and other robot confirm to help.
- Abandoned: The plan is no longer necessary or relevant.

#### Input #### 
=== Current Status ===
{current_status}

=== Robot Pool ===
The Robot Pool has several robots available. If you and your teammates are unable to handle the task, you can use [request_new_member] to specify the request number and the required capabilities of the new member.

=== Task Progress ===
{task_progress}

=== Last Subtask ===
{current_subtask}

=== Action History ===
{action_history}

=== Last Round Facts ===
{facts}

=== Last Round Communication Goal ===
{communication_goal}

=== Dialogue History ===
{dialogue_history}

### Response Format ###
<Thinking>
Step-by-step reasoning about the updated communication plan and facts based on latest information.

<Answer>
```json
{{
    "facts": ["The facts about the communication goal"],  
    "plan": [["plan_type", "plan_status", "The updated detailed communication plans"]]  # plan_type: Information Synchronization, Task Assignment, Requesting Assistance, Requesting New Member from Robot Pool or Offer help; plan_status: "In progress" or "Complete"
}}
```

Note:
1) When handling a replacement task, complete it independently if possible. Don't take two or more replacement tasks at the same time. Assign tasks to teammates to improve efficiency.
2) Priority replacement task, when no replacement subtask do explore.
3) Take action to complete the replacement task as quickly as possible. Do not wait for teammates to act unless collaborating to move heavy objects.
4) You can only explore rooms: {all_rooms}, No room called "Hallway"; only do subtask in shown in **task progress**
5) Try to take different tasks with your teammates unless pull heavy object together. [replace] can be done independently.
6) Take a not complete task when you have time and no other task to do. You can offer help if you are idle or take a explore task.
7) Priority do replacement task, when no replacement subtask do explore.
8) You can request new member to handle replacement subtask if all robots are busy.
"""

comm_task_evaluation_prompt = """You are {robot_name}, a member of a heterogeneous robot team focused on efficiently exploring all known rooms and completing the repositioning tasks outlined in the task progress.

You have just completed a communication with your teammates, specifically the most recent comm_step. 

Based on the **Current Status**, **Task Progress**, **Action History**, and **Dialogue History**, summarize the task you should currently undertake. Pay particular attention to the most recent action history and the communication content from the latest communication step, as you have just concluded this round of communication. If there is no clearly defined task to take on, proceed with an incomplete task that still needs to be addressed.

### Inputs ###
=== Current Status ===
{current_status}

=== Task Progress ===
{task_progress}

=== Action History ===
{action_history}

=== Dialogue History ===
{dialogue_history}

### Subtask Format ###
- [replace] <object> <target_position>  # object can be pick and place is small object, like apple, pillow, etc.
- [explore] <room_name>  # explore the room that not explored yet
- [gopull] <object>  # object can pull is big furniture, like bed, sofa, etc.


### response format ###
<Thinking>
Step-by-step reasoning of the current subtask, collaboration_members, other_robot_subtask, subtask_progress, and brief_subtask_description.

<Answer>
```json
{{
    "current_subtask": "[replace] <object> <target_position>  or  [explore] <room>  or  [pull] <object>", 
    "other_robot_subtask": [("Robot_name", "subtask")],
    "collaboration_members": "List of teammates involved in the current task.",  # only pull together need collaboration_members
    "next_confirmed_subtasks": "next subtasks that i confirmed to dp."
}}
```

Note:
1) Only do subtask not complete shown in the **task progress**. If target position is not known, do [explore] <room> to find possible target position.
2) Pay attention the task confirmation and rejection in the dialogue history
3) Pay attention to the correct task progress, the only dependency is the action history you have done, and the task progress.
4) Try to take different tasks with your teammates unless pull heavy object together. [replace] can be done independently.
5) Take a not complete task and take action when you have time and no other task to do.
6) **Pay special attention** if you are confirmed [gopull] with other robots in communication, your subtask is [gopull] if you confirm to help [gopull] something!
7) Always prioritize replacing any misplaced objects in your current room by relocating them to the nearest appropriate position—preferably within the same room—before considering any other tasks.
"""

action_prompt_template = """You are {robot_name}, a member of a heterogeneous robot team focused on efficiently exploring all known rooms and completing the repositioning tasks outlined in the task progress.

Your primary goal is to determine the next action required to complete the current subtask based on the task evaluation, progress, and recent history. Use the provided inputs to reason step-by-step and produce a structured decision.

### Input ###
=== Current Status ===
{current_status}

=== Task Progress ===
{task_progress}

=== Current Subtask ===
{current_subtask}

=== Action History ===
{action_history}

=== Available Action ===
You should keep '[]' and '<>' in your output and replace content within it, eg. [explore] <roomA>, [gopick] <apple>, [goplace] <table>, [gopull] <bed>, [exit]

Select the next action from the following action space:
{action_space}

### Response format ###
<Reasoning>
Analyse current task progress, the action history realted subtask, then determine the next action.

<Answer>
```json
{{
    "action": " Next action to be performed"
}}
```

Note:
1) Action Space: You can only select actions from the given action space.
2) Take a not complete task and no one handled and take action when you have time and no other task to do.
3) PRIORITY doing your **current subtask**. If subtask is [explore], and the room is not in **Action Space**, try to explore other room.
4) When do subtask [replace]: [gopick] when not holding target object, [goplace] when holding target object. 
5) When do subtask [gopull]: **directly do [gopull]** and not [explore] anymore.
6) [exit] when your subtask is [exit] and you don't hold any object or you have nothing todo.If hold object, do [goplace] to place it.
"""

misplaced_detect_prompt = """You are an intelligent assistant specialized in understanding household arrangements. 

You only need to detect whether there are misplaced objects on the floor. For example, objects like pillows, toilet paper, and newspapers placed on the floor are considered unreasonable. Anything not "on the floor" is considered reasonable.

=== Object You Need to Analyze ===
{obj_and_description}

=== Examples ===
=== input ===
1. Pillow - pillow is on the floor, between the bed and the wall.
2. Toilet_paper - toilet paper is on the flush_toilet.
3. Pot - Pot is on the oven.
=== output ===
<Reasoning>
1. Pillow is on the floor, which is unreasonable. Pillow typically on the bed or sofa.
2. Toilet_paper is on the flush_toilet, which is reasonable. Toilet paper typically on the flush_toilet.
3. Pot is on the oven, which is reasonable. Pot typically on the oven. 

So, the misplaced objects are: pillow.
<Answer>
```json
{{
    "misplaced_object": ["pillow"]
}}
```


=== Output Format ===
Provide a JSON response with two fields:
1. `thought`: A step-by-step reasoning for why certain objects are misplaced (if any).
2. `misplaced_object`: A list of misplaced object names, or "None" if all objects are reasonably placed.

=== Response Example ===
<Reasoning>
The pillow_1 should not be on the floor because it is typically used on a bed. The slippers_1 on the table are unreasonable as they are worn on feet and belong near the floor. The cd_1 on the window_sill, which is a reasonable location for it.
<Answer>
```json
{{
    "misplaced_object": ["pillow_1", "slippers_1"] or "None"
}}
```

Note: 
1) all objects are in lowercase with format "object_type"_"index", eg. pillow_1, table_2. Pay attention to the object type and index.
2) Only detect misplaced things "on" floor, ignore others.
"""

misplaced_object_container_reason_prompt = """You are an expert assistant for determining reasonable locations for objects in a household setting. Your task is to infer new, reasonable locations for the given objects based on their context and the household environment. Use logical reasoning and consider typical household norms when suggesting new locations.

=== Known Object and Container ===
{obj_and_container}

=== Known Container ===
{known_container}

=== Response Format ===
```json
{{
    thought": "xxx" # Step-by-Step reasoning for determining new reasonable locations for each object.,
    "updated_obj_and_container": {{
        "object_name1": ["new_container1", "new_container2"],
        "object_name2": ["new_container3"],
        ...
    }}
}}
```

Note:
1) If known reasonable locations exist for an object, add new, reasonable ones without duplicating.
2) If no reasonable location is found in **Known Container**, return an empty list if no suitable location can be determined.
3) all objects are in lowercase with format "object_type"_"index", eg. pillow_1, table_2. Pay attention to the object type and index.
4) all **Known Object and Container** should be in the **updated_obj_and_container** and as the key of the dictionary.
5) all **container** in the **updated_obj_and_container** must be in the **Known Container**, don't response the container that is not in the **Known Container**.
"""

success_reflection_prompt = """You are {robot_name}, a member of a heterogeneous robot team focused on efficiently exploring all known rooms and completing the repositioning tasks outlined in the task progress.

Based on your current state, dialogue history, previous actions, current success action. Decide whether need to communicate with other robots to update the task progress or not.

### Input ###
=== Current State ===
{current_state}

=== Dialogue History ===
{dialogue_history}

=== Current In Progress Action ===
Action: {action}



### Response Format ###
```json
{{
    "thoughts": "xxx",  # Step-by-step reasoning for the action and communication necessary.
    "comm_flag": "Yes" or "No"  # Whether communication with other robots is needed.
    "comm_goal": "xxx" or "None" # brief description of the communication goal. If no communication is needed, set to "None".
}}
```

Note you can only choose the action in the action space.
"""

failed_reflection_prompt = """You are {robot_name}, a member of a heterogeneous robot team focused on efficiently exploring all known rooms and completing the repositioning tasks outlined in the task progress.

Based on your current state, dialogue history, previous actions, current action, and result feedback, reflect on the reason for the action failure and propose possible solutions. Then, decide whether to resolve the issue independently or seek assistance from teammates through communication or task reallocation.


### Input ###
=== Current Subtask ===
{subtask}

=== Task Progress ===
{task_progress}

=== Previous Action ===
{action_history}

=== Current Failed Action ===
Failed Action: {action}
Feedback: {feedback}

### Response Format ###
```json
{{
    "thoughts": "xxx",  # Step-by-step reasoning for the action reflection.
    "reflection": "xxx",   # Brief reason for failure.
    "solution": "xxx", # Proposed solution to resolve the issue.
    "comm_flag": "Yes" or "No"  # Whether communication with other robots is needed.
}}
```

Note:
1) When [gopull] <bed> or [gopull] <sofa> alone and failed because of lack of strength, you have no choice but to communicate with other robots to help you pull.
2) When [gopull] <bed> or [pull] <sofa> with your teammates, and teammates not come yet, you should continue [gopull] until teammates come. If teammates come, and still failed because of lack of strength, you should communicate with other robots to help you pull.
3) The feedback of [gopull] if have Robot's name, means this robots have come and pulled together. If only have your strength, means you pull alone.
"""

dispatch_robot_prompt_single = """You are {robot_name}, your capacity is {capacity}.

Your task is to analyze based on your own **capacity** and **current situation** determine whether need new member from robot_pool to help finish task.

If need, determine the minimal team of robots from the Robot Pool required to fulfill the request.

### Input ###
=== Robot Pool ===
{robot_pool}

=== Current Situation ===
{reflection_message}

### Response Format ###
=== Reasoning ===
Step-by-step reasoning based on your own **capacity** and **current situation**, decide whether need new member from robot_pool.
If need analyse the minimal team of robots from the Robot Pool required to fulfill the request.

=== Answer ===
```json
{{
    "robot_list": ["robot_name1", "robot_name2", ...],  # List of robot names to dispatch from the pool.
}}
```

Note:
1) Robot name should be formated as Robot_x, x is the number of the robot.
2) Dispatch the smallest possible team that fully meets the requirements for dispatch.
3) Strictly adhere to the requested number of robots and aim to meet the required capability as closely as possible. If the capability requirement cannot be fully satisfied, dispatch the closest available option. For example, if a robot with an operational capacity exceeding 80N is requested but unavailable, send a robot with a 60N operational capacity as a substitute.
4) Avoid returning an empty list unless there are no available robots.
"""

dispatch_robot_prompt = """You are an intelligent reasoning assistant. 

Your task is to analyze the request message and determine the minimal team of robots from the Robot Pool required to fulfill the request.

Strictly adhere to the requested **number** of robots and aim to meet the required capability as closely as possible. If the capability requirement cannot be fully satisfied, dispatch the closest available option. For example, if a robot with an operational capacity exceeding 80N is requested but unavailable, send a robot with a 60N operational capacity as a substitute.

### Input ###
=== Robot Pool ===
{robot_pool}

=== Request Message ===
{request_message}

### Response Format ###
=== Reasoning ===
Step-by-step reasoning based on the number of robots and capabilities in **request message**, robot pool.

=== Answer ===
```json
{{
    "robot_list": ["robot_name1", "robot_name2", ...],  # List of robot names to dispatch from the pool.
}}
```

Note:
1) Robot name should be formated as Robot_x, x is the number of the robot.
2) Dispatch the smallest possible team that fully meets the requirements for dispatch.
3) Strictly adhere to the requested number of robots and aim to meet the required capability as closely as possible. If the capability requirement cannot be fully satisfied, dispatch the closest available option. For example, if a robot with an operational capacity exceeding 80N is requested but unavailable, send a robot with a 60N operational capacity as a substitute.
4) Avoid returning an empty list unless there are no available robots.
"""

pull_purpose_prompt = """You are {robot_name}, you will do the action: {action}, [gopull] action is to clear way for other robots to [gopick] something.
Based on dialogue history, action history, determine what is robot's target object to [gopick] after [gopull] action from **possible object**.

### Inputs ###
=== Dialogue History ===
{dialogue_history}

=== Action History ===
{action_history}

### Possible Object ###
{possible_object}

### Response Format ###
<Reasoning>
Step-by-step reasoning based on the dialogue history, action history, and possible object to determine the target object to [gopick] after [gopull] action.

<Answer>
```json
{{
    "target_object": "object_name"
}}
```
"""