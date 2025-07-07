import json
import os
import random
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pprint import pprint

from termcolor import colored

from check_result import check_relation
from communicator import MultiRobotCommunicator, round_robin_communicate
from dispatch_robot import DispatchRobot
from llm import completion
from logger_manager import LoggerManager
from prompts import dispatch_robot_prompt_single
from tools import (
    ItemMapper,
    get_closest_match,
    get_robot_observation,
    init_config,
    modify_actions,
    parse_json_from_response,
    process_observation,
    robot_name_formulation,
)

REMOTE_URL = json.load(open('args/select_args.json','r'))["remote_url"]
port = REMOTE_URL.split(":")[-1].replace("/", "")


scene_index = json.load(open("args/select_args.json", "r"))["scene"]

SAVE_DIR = f"output/120_ours/{scene_index}"
LOG_DIR = f"logs/120_ours/{scene_index}/{port}"

DATASET_DIRECT = f"datasets/dataset_s{scene_index}_72.json"

LOG = True
DEBUG = True
COMM_ALGORITHM = 0  # 0: Flexible, 1: Round Robin
TALK_ALGORITHM = 0  # 0: plan-action, 1: action
TALK_ALGORITHM = "plan" if TALK_ALGORITHM == 0 else "action"
MAX_STEP = 100
MAX_COMM_STEP = 50
MAX_TIME_STEP = 2500
ROOMS = None
item_mapper = ItemMapper()


def get_dispatched_list(request_robot, reflection, robot_pool):
    robot_pool_info = ""
    for robot in robot_pool:
        robot_pool_info += f"name: {robot.name}, {robot.capacity}\n"
    prompt = dispatch_robot_prompt_single.format(
        robot_name=robot.name, 
        capacity=robot.capacity, 
        reflection_message=reflection, 
        robot_pool=robot_pool_info)
    response = completion(prompt)["response"]
    robot_list = parse_json_from_response(response, "robot_list")
    if isinstance(robot_list, str):
        robot_list = [robot_list]
    if len(robot_list) == 0:
        print(colored(f"{request_robot.name} Failed in request new member: {robot_list};\n", "yellow"))
        return None
    elif "none" in robot_list[0].lower():
        print(colored(f"{request_robot.name} Failed in request new member: {robot_list};\n", "yellow"))
        return None
    else:
        print(colored(f"{request_robot.name} request to dispatch robots: {robot_list};\n", "yellow"))
        return robot_list

def get_robot_by_name(name, all_robots):
    for robot in all_robots:
        if robot.name == name:
            return robot

def get_teammates_info(robot_pool, robot_team):
    pool_teammates = []
    for robot in robot_pool:
        pool_teammates.append(f"name:{robot.name}, {robot.capacity}")

    for robot in robot_team:
        teammates = []
        for r in robot_team:
            if r.name != robot.name:
                teammates.append(f"name: {r.name}, {r.capacity}")
        robot.teammates = teammates
        robot.pool_teammates = "; ".join(pool_teammates)


def run(dataset_id=0):
    # Init
    success_place_count = 0
    place_object_time_step = {}
    total_member = 0
    start_time = time.time()
    env, robot_pool, robot_team, ROOMS, misplaced_objects = init_config(dataset_id, DATASET_DIRECT)
    task_num = len(misplaced_objects)
    last_team_size = len(robot_team)
    initial_team_size = len(robot_team)
    total_comm_cost = 0
    step_comm_cost = {}
    
    dispatch_robot = DispatchRobot()
    all_robot = robot_pool + robot_team
    step = 0
    stop = False
    comm_step = 0
    comm_purpose = {
        robot.name: [
            "Begin of task, you and your teammates need to explore different room first."
        ]
        for robot in robot_team
    }

    for robot in robot_team:
        robot.room = env.get_robot_room(robot.name)

    while comm_step < MAX_COMM_STEP:
        if stop:
            break
        comm_step += 1
        print()
        print(colored(f"======== Comm Step {comm_step} ======== ", "blue"))
        print(colored("===== Comm ===== ", "blue"))
        get_teammates_info(robot_pool, robot_team)

        for r in robot_team:
            r.comm_step = comm_step

        # communication Agent represent robot to communicate
        if COMM_ALGORITHM == 0:
            for robot in robot_team:
                purpose = comm_purpose.get(robot.name)
                if len(purpose) > 0:
                    robot.communication_agent.purpose = "\n".join(purpose)
                else:
                    robot.communication_agent.purpose = None
                robot.communication_agent.phase = 0

            with MultiRobotCommunicator(
                robot_team, robot_pool, env, comm_step, debug=True
            ) as communicator:
                robot_team, robot_pool, current_round_dialogue, comm_cost = (
                    communicator.communicate()
                )
                total_comm_cost += communicator.communication_cost
            robot_team = robot_team
            robot_pool = robot_pool

        elif COMM_ALGORITHM == 1:
            round_robin_communicate(robot_team, comm_step)
        else:
            raise ValueError(f"Invalid COMM_ALGORITHM: {COMM_ALGORITHM}")

        # Add Comm Step to action history
        for robot in robot_team:
            # env.robot_room[robot.name] = robot.location
            robot.action_history.append(f"Finish Comm Step {comm_step}")

        # after comm subtask update
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(
                    lambda robot=robot: (
                        robot.name,
                        robot.progress_agent.after_comm(
                            robot.get_current_state(),
                            robot.get_task_progress(),
                            robot.get_last_subtask(),
                            robot.get_action_history(),
                            robot.get_communication_history(),
                        ),
                    )
                )
                for robot in robot_team
                if len(current_round_dialogue.get(robot.name)) > 0
            ]
            for future in futures:
                robot_name, ret = future.result()
                r = get_robot_by_name(robot_name, all_robot)
                if r:
                    r.last_subtask = ret
                print()
                print(f"{robot_name} last subtask: {ret}")
                print()

        # ========= [Action <-> Reflection] loop =========
        comm_purpose = {
            robot.name: [] for robot in all_robot
        }  # comm purpose for comm plan
        last_actions = {
            robot.name: None for robot in robot_team
        }  # last action for each robot
        comm_flags = {
            robot.name: False for robot in robot_team
        }  # if comm flag for each robot
        continue_last_action_robot = []  # robots that need to continue last action and do not need to act decision, eg. explore or goto in progress

        if step >= MAX_STEP or env.total_time_step >= MAX_TIME_STEP:
            stop = True
        while step < MAX_STEP and env.total_time_step < MAX_TIME_STEP:
            total_member = max(total_member, len(robot_team))
            if stop:
                break
            step += 1
            for r in robot_team:
                r.step = step

            # if (
            #     len(robot_team[0].unexplored_rooms) == 0
            #     and len(robot_team[0].misplaced_obj_and_container) == 0
            # ):
            #     print(
            #         colored(
            #             "All rooms have been explored and all misplaced objects have been handled.",
            #             "red",
            #         )
            #     )
            #     stop = True
            #     break

            # Action Decision
            robot_actions = {}
            with ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(
                        lambda robot=robot: (
                            robot.name,
                            robot.action_agent.act(
                                robot.get_current_state(),
                                robot.get_task_progress(),
                                robot.get_last_subtask(),
                                robot.get_action_history(),
                                robot.get_communication_history(),
                                robot.get_action_space(env, item_mapper),
                                robot.scene_graph,
                                list(robot.misplaced_obj_and_container.keys()),
                                item_mapper,
                                ROOMS,
                            ),
                        )
                    )
                    for robot in robot_team
                    if robot.name
                    not in continue_last_action_robot  # robots that need to act decision
                ]
                for future in futures:
                    robot_name, ret = future.result()
                    robot_actions[robot_name] = ret

            for robot, action in last_actions.items():
                if robot in continue_last_action_robot:
                    robot_actions[robot] = last_actions[robot]
            last_actions = robot_actions

            # formal actions
            modified_actions = modify_actions(robot_actions, item_mapper, ROOMS)

            print()
            print(colored(f"====== Step {step} ======", "blue"))
            print(colored("===== Action ===== ", "blue"))
            pprint(robot_actions)
            print()

            step_comm_cost[step] = total_comm_cost
            action_result = env.co_act(modified_actions)

            for robot in robot_team:
                robot.room = env.get_robot_room(robot.name)

            # init continue action robot
            continue_last_action_robot = []

            for robot in robot_team:
                need_reflection = False
                flag_message = None
                in_progress = False

                print(colored(f"======== {robot.name} ======== ", "green"))
                print(f"Action: {robot_actions[robot.name]}")
                print("Result: ")
                pprint(action_result[robot.name])

                if DEBUG:
                    print(f"Explored: {robot.explored_rooms}")
                    print(f"Unexplored: {robot.unexplored_rooms}")
                    print(robot.misplaced_obj_and_container)
                    print(robot.holding_object)

                result = action_result[robot.name]
                flag = result["flag"]
                message = result["message"]
                observation = result["observation"]
                action = robot_actions[robot.name]
                reflection = None

                # ===== process_observation =====
                if observation:
                    obs = process_observation(observation, item_mapper)
                    robot.observation, new_obj_dict = robot.get_observation(obs)
                    for r in robot_team:
                        _, _ = r.get_observation(obs)

                    # detect misplaced object
                    if len(new_obj_dict) > 0:
                        (
                            detect_misplaced_obj_flag,
                            update_container_flag,
                            updated_obj_and_container,
                            misplaced_str,
                        ) = robot.observation_agent.act(
                            robot.misplaced_obj_and_container,
                            new_obj_dict,
                            robot.placeable_objects,
                        )

                    else:
                        detect_misplaced_obj_flag = False
                        update_container_flag = False
                        updated_obj_and_container = robot.misplaced_obj_and_container
                        misplaced_str = "No misplaced object detected."

                    # get room for misplaced object and container
                    if len(updated_obj_and_container) > 0:
                        for obj, containers in updated_obj_and_container.items():
                            if "none" in obj.lower() or obj not in robot.scene_graph:
                                obj_and_container = {
                                    o: updated_obj_and_container[o]
                                    for o in updated_obj_and_container
                                    if o != obj
                                }
                                for r in robot_team:
                                    r.misplaced_obj_and_container = obj_and_container
                                continue
                            robot.scene_graph[obj]["room"] = env.get_object_room(
                                item_mapper.get_env_object_id(obj)
                            )
                            print(f"Updated misplaced object: {obj}")
                            room = robot.scene_graph[obj]["room"]
                            if "none" not in room.lower():
                                print(f"room: {room}")
                            for c in containers:
                                if "none" in c.lower() or c not in robot.scene_graph:
                                    continue
                                robot.scene_graph[c]["room"] = env.get_object_room(
                                    item_mapper.get_env_object_id(c)
                                )
                                print(f"Updated container: {c}")
                                room = robot.scene_graph[c]["room"]
                                if "none" not in room.lower():
                                    print(f"room: {room}")
                        robot.misplaced_obj_and_container = updated_obj_and_container
                        for r in robot_team:
                            r.misplaced_obj_and_container = updated_obj_and_container

                    # if detect misplaced object, need to reflect
                    if detect_misplaced_obj_flag or update_container_flag:
                        print(f"\n{robot.name} : {misplaced_str}\n")

                    if detect_misplaced_obj_flag:
                        # detect new misplaced object, need reflection
                        continue_last_action_robot = [
                            r for r in continue_last_action_robot if r != robot.name
                        ]
                        comm_flags[robot.name] = True
                        comm_purpose[robot.name].append(
                            misplaced_str
                            + "I need to broadcast to my teammates, and confirm who handle it."
                        )
                        reflection = misplaced_str
                        feedback = misplaced_str
                        if len(robot_team) == 1:
                            dispatched_robot_list = get_dispatched_list(robot, reflection, robot_pool)
                            if dispatched_robot_list:
                                robot_pool, robot_team = dispatch_robot.dispatch_robot(robot.name, reflection, dispatched_robot_list, env, robot_pool, robot_team)
                                dispatch_robot.update_teammates_info(robot_pool, robot_team)
                                robot.action_history.append(f"Step_{step} - {action} - {flag}")
                                break
                    else:
                        feedback = "Not detect misplaced object on the way."

                # ==== process action result ====
                if "explore" in action:
                    if flag:
                        room = action.split("<")[1].split(">")[0]
                        robot.last_subtask = "None"
                        robot.explored_rooms.append(room)
                        robot.explored_rooms = list(set(robot.explored_rooms))
                        robot.unexplored_rooms = list(
                            set(ROOMS) - set(robot.explored_rooms)
                        )
                        for r in robot_team:
                            r.explored_rooms = robot.explored_rooms
                            r.unexplored_rooms = robot.unexplored_rooms
                        # comm_flags[robot.name] = True
                        comm_purpose[robot.name].append(
                            f"I have complete {action}. Broadcast to my teammates, they do not need to explore the same area. And confirm my new task."
                        )

                    else:
                        in_progress = True
                        continue_last_action_robot.append(robot.name)
                        continue_last_action_robot = list(
                            set(continue_last_action_robot)
                        )

                if "gopick" in action:
                    object_name = action.split("<")[1].split(">")[0]
                    if flag:
                        continue_last_action_robot = [
                            r for r in continue_last_action_robot if robot.name != r
                        ]
                        robot.holding_object = object_name

                    else:
                        # too far, or holding things
                        if "out of arm" in message.lower():
                            need_reflection = True

                            feedback = (
                                "The area around the object is inaccessible."
                                + f" - {robot.scene_graph[object_name]['description']}"
                            )

                        else:
                            feedback = message

                if "goplace" in action:
                    if flag:
                        success_place_count += 1
                        comm_flags[robot.name] = True
                        comm_purpose[robot.name].append(
                            f"I finished the subtask {action}, need to confirm next subtask."
                        )

                        holding_object = action.split("<")[1].split(">")[0]
                        placed_container = action.split("<")[2].split(">")[0]
                        place_object_time_step[holding_object] = env.total_time_step
                        holding_object = get_closest_match(holding_object, robot.misplaced_obj_and_container.keys())
                        # robot.misplaced_obj_and_container = {
                        #     obj: robot.misplaced_obj_and_container[obj]
                        #     for obj in robot.misplaced_obj_and_container
                        #     if obj != holding_object
                        # }
                        robot.misplaced_obj_and_container = {
                            obj: (
                                robot.misplaced_obj_and_container[obj]
                                if len(robot.misplaced_obj_and_container[obj]) == 1
                                else [container for container in robot.misplaced_obj_and_container[obj] if container != placed_container]
                            )
                            for obj in robot.misplaced_obj_and_container
                            if obj != holding_object
                        }
                        robot.holding_object = None
                        robot.complete_misplaced_task.append(holding_object)
                        robot.complete_misplaced_task = list(
                            set(robot.complete_misplaced_task)
                        )
                        for r in robot_team:
                            r.misplaced_obj_and_container = (
                                robot.misplaced_obj_and_container
                            )
                            r.complete_misplaced_task = robot.complete_misplaced_task

                        robot.last_subtask = "Don't have any task now."

                if "gopull" in action:
                    if flag:
                        comm_flags[robot.name] = True
                        comm_purpose[robot.name].append(
                            f"I have complete {action} clear the way to pick. I can do [replace] task next."
                        )
                        object_name = action.split("<")[1].split(">")[0]
                        for r in robot_team:
                            r.moveable_objects = [o for o in r.moveable_objects if o != object_name] 
                    else:
                        need_reflection = True

                # [goto] on the way
                if message:
                    if "on the way" in message.lower():
                        continue_last_action_robot.append(robot.name)
                        continue_last_action_robot = list(
                            set(continue_last_action_robot)
                        )

                if "exit" in action:
                    env.robot_team.remove(robot.name)
                    env.set_robot(env.robot_team)
                    robot_pool.append(robot)
                    robot_team = [r for r in robot_team if r != robot]
                    print(f"Length of robot_team: {len(robot_team)}")
                    print(f"Length of robot_pool: {len(robot_pool)}")
                    print(
                        colored(
                            f"{robot.name} has been removed from the team.", "yellow"
                        )
                    )
                    get_teammates_info(robot_pool, robot_team)
                    # send stop message
                    for r in robot_team:
                        r.communication_agent.memory.append(
                            f"{robot.name} has been removed from the team."
                        )

                if len(robot_team) == 0:
                    stop = True
                    break

                if need_reflection:
                    comm_flag, reflection = robot.reflection_agent.act(
                        robot.get_task_progress(),
                        robot.last_subtask,
                        robot.get_current_state(),
                        robot.communication_agent.memory,
                        action,
                        flag,
                        feedback,
                        robot.get_action_history,
                    )
                    if comm_flag:
                        comm_flags[robot.name] = True
                        comm_purpose[robot.name].append(reflection)
                        if len(robot_team) == 1:
                            dispatched_robot_list = get_dispatched_list(robot, reflection, robot_pool)
                            if dispatched_robot_list:
                                robot_pool, robot_team = dispatch_robot.dispatch_robot(robot.name, reflection, dispatched_robot_list, env, robot_pool, robot_team)
                                dispatch_robot.update_teammates_info(robot_pool, robot_team)
                                robot.action_history.append(f"Step_{step} - {action} - {flag}")
                                break
                
                # Set flag message
                if in_progress:
                    flag_message = "In progress"
                elif flag:
                    flag_message = "Success"
                else:
                    flag_message = "Failed"

                # action record
                action_record = f"Step_{step} - {action} - {flag_message}"
                if reflection and "none" not in reflection.lower():
                    action_record += f"\n    Reflection: {reflection}"
                    print(action_record, comm_flags[robot.name])
                    print()
                robot.action_history.append(action_record)

            if_comm = False
            for robot, comm_flag in comm_flags.items():
                if_comm = if_comm or comm_flag

            if len(robot_team) == 0:
                stop = True
                break

            if (
                len(robot_team[0].unexplored_rooms) == 0
                and len(robot_team[0].misplaced_obj_and_container) == 0
                # and success_place_count >= task_num
            ):
                print(
                    colored(
                        "All rooms have been explored and all misplaced objects have been handled.",
                        "red",
                    )
                )
                stop = True
                break

            if if_comm:
                break
        partial_success_rate = success_place_count / task_num

    temporal_step = env.total_time_step
    action_step = env.total_route_step
    team_number_time_step = env.team_each_time_step
    last_time_step = 0
    total_count = 0
    external_help_count = 0

    for time_step, info in team_number_time_step.items():
        duration_time = time_step - last_time_step
        total_count += info['member_count'] * duration_time
        last_time_step = time_step

        if info['member_count'] > last_team_size:
            external_help_count += 1
        last_team_size = info['member_count']

    average_team_size = total_count / temporal_step
    total_time = (time.time() - start_time) / 60
    object_neighbors, relations = env.check_result(misplaced_objects)
    
    if_success, rule_success_rate, llm_succuss_rate, partial_success_rate, res = check_relation(relations)
    
    with open(DATASET_DIRECT, "r") as f:
        dataset = json.load(f)
        missed_num = dataset[dataset_id]["object_count"]["missed"]
        trapped_num = dataset[dataset_id]["object_count"]["trapped"]

    save_info = {}
    save_info["step_comm_cost"] = step_comm_cost
    save_info["dataset_id"] = dataset_id
    save_info["missed_num"] = missed_num
    save_info["trapped_num"] = trapped_num
    print("=== object neighbors ===")
    pprint(object_neighbors)
    save_info["object_neighbors"] = object_neighbors
    print()
    print("=== relations ===")
    pprint(relations)
    save_info["relations"] = relations
    print("=== result ===")
    pprint(res)
    save_info["res"] = res
    print()
    print("=== team number time step ===")
    pprint(team_number_time_step)
    save_info["team_number_time_step"] = team_number_time_step
    print()
    # print(colored("===== Policy =====", "blue"))
    # print(colored(f"Using Team Policy: {TEAMING_MAPPING_DICT[TEAMING_POLICY]}"))
    # print(colored(f"Using Action Policy: {ACTION_MAPPING_DICT[ACTION_POLICY]}"))
    print(colored(f"Initial Team Size: {initial_team_size}"))
    save_info["initial_team_size"] = initial_team_size
    print()
    print(colored("===== If Success =====", "blue"))
    print(colored(f"Success : {if_success}"))
    save_info["success"] = if_success
    print()
    print(colored("===== Metrics =====", "blue"))
    print(colored(f"Rule_Partial Success Rate: {rule_success_rate}"))
    print(colored(f"LLM_Partial Success Rate: {llm_succuss_rate}"))
    print(colored(f"Partial Success Rate: {partial_success_rate}"))
    save_info["rule_success_rate"] = rule_success_rate
    save_info["llm_success_rate"] = llm_succuss_rate
    save_info["partial_success_rate"] = partial_success_rate
    print(colored(f"   - place_object_time_step: {place_object_time_step}"))
    save_info["place_object_time_step"] = place_object_time_step
    if not if_success:
        temporal_step = MAX_TIME_STEP
    print(colored(f"Total Time Step: {temporal_step}"))
    save_info["temporal_step"] = temporal_step
    print(colored(f"Total Action Step: {action_step}"))
    save_info["action_step"] = action_step
    print(colored(f"Total Active Robots: {total_member}"))
    save_info["total_member"] = total_member
    print(colored(f"Average Team Size: {average_team_size}"))
    save_info["average_team_size"] = average_team_size
    print(colored(f"External Help Count: {external_help_count}"))
    save_info["external_help_count"] = external_help_count
    print(colored(f"Total comm cost: {total_comm_cost}", "red"))
    save_info["total_comm_cost"] = total_comm_cost
    print(colored(f"Total time: {total_time} min", "red"))
    save_info["total_time"] = total_time

    # 保存 save info
    save_dir = SAVE_DIR
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    with open(f"{save_dir}/dataset_{dataset_id}.json", "w") as f:
        json.dump(save_info, f, indent=2)

    return if_success

if __name__ == "__main__":
    SCRIPT_COUNT = 5
    SCRIPT_NUM = 4

    print("using port: ", port)
    print("total script count: ", SCRIPT_COUNT)
    print("this script number: ", SCRIPT_NUM)

    if LOG:
        log_manager = LoggerManager(LOG_DIR)
        logger = log_manager.get_logger()

    total_success_count = 0
    total_count = 0
    with open(DATASET_DIRECT, "r") as f:
        dataset_length = len(json.load(f))

    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    total_data = dataset_length
    existed_result_files = os.listdir(SAVE_DIR)
    existed_result_ids = [int(rf.split('.')[0].split('_')[1]) for rf in existed_result_files]
    max_test_num = 5
    test_iter = 1


    while test_iter < max_test_num and len(existed_result_ids) < total_data:
        test_iter += 1 
        # for i in range(dataset_length):# 正向
        for i in range(dataset_length - 1, -1, -1):# 逆向
            print(f"========= Dataset {i} =========")
            print("=================================")
            if i in existed_result_ids:
                continue
            if i % SCRIPT_COUNT != SCRIPT_NUM:
                print("jump", i)
                continue
            try:
                total_count += 1
                if_success = run(i)
                if if_success:
                    total_success_count += 1
                existed_result_files = os.listdir(SAVE_DIR)
                existed_result_ids = [int(rf.split('.')[0].split('_')[1]) for rf in existed_result_files]
            except Exception as e:
                print(e)
                traceback.print_exc()
                print("==== Error in dataset ====", i)

    success_rate = total_success_count / dataset_length
    print()
    print(success_rate)
    print(total_success_count)
    print(total_count)

    if LOG:
        log_manager.close()