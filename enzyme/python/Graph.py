from cmath import inf
from dis import Instruction
from platform import node
import matplotlib.pyplot as plt
from LevelInfo import LevelInfo
from RegFile import RegisterFile

STEP = 10
def get_dict_from_file(filename):
    """
    Reads a file and returns a dictionary with the content.
    """
    res = {}
    with open(filename, 'r') as f:
        for line in f:
            rev_var, var = [i.strip() for i in line.split(',')]
            if rev_var != var:
                res[rev_var] = var
        return res

class Node:
    unique_id = 0
    instruction_id = 0
    def __init__(self, id, occurance, parents, type, mode='F', actual_level=0):
        self.id = id
        self.uid = None
        self.occurance = occurance
        self.children = []
        self.parents = parents
        self.type = type
        self.cost = sum(i.cost for i in parents) + 1
        self.level =  0
        self.actual_level = actual_level
        self.end_level = 0
        self.mode = mode
        self.liveness = ()
        self.contains_edge = False
        self.instruction_id = Node.instruction_id + 1
        Node.instruction_id += 1

        self.is_allocated = False
        # if mode == 'F' and 'root' not in self.type:
        #     self.uid = Node.unique_id +1
        #     Node.unique_id += 1

    def to_inst(self):
        child_list = sorted([node.instruction_id for node in self.children])
        return Instruction(self.id, self.type, self.instruction_id, self.parents[0].instruction_id, self.parents[1].instruction_id if len(self.parents) > 1 else None, child_list)

    def get_next_use(self, level, consider_edge=True):
        distance = inf
        for child in self.children: 
            if (self.mode == child.mode or consider_edge) and child.actual_level > level: # check if node -> child is not an edge
                distance = min(distance, child.actual_level - level)
        return distance

    def add_child(self, node):
        self.children.append(node)
        if  self.is_forward() and node.is_reverse() and not self.contains_edge:
            self.contains_edge = True
    
    def has_children(self):
        return len(self.children) > 0

    def is_address(self):
        return self.type == 'address'

    def is_forward(self):
        return self.mode == 'F'

    def is_reverse(self):
        return self.mode == 'R'
    
    def is_root(self):
        return 'root' in self.type

    def is_load(self):
        return self.type == 'load'

    def is_store(self):
        return self.type == 'store'

    def is_arithmetic(self):
        return 'arithmetic' in self.type
    
    def is_arg(self):
        return 'arg' in self.type

    def is_mem_op(self):
        return self.type == 'load' or self.type == 'store'

    def get_address(self):
        if self.is_load():
            return self.parents[-1].id
        elif self.is_store():
            return self.id
        return None

    def update_parent_actual_liveness(self):
        for parent in self.parents:
            if parent.actual_level > self.actual_level:
                print(parent, self)
            if parent.is_forward() and parent.actual_level > self.actual_level:
                print("Parent: {}, level: {}, node: {}, level: {}".format(parent, parent.actual_level, self, self.actual_level))
            if parent.end_level < self.actual_level:
                parent.end_level = self.actual_level

    def update_children_actual_liveness(self, amount):
        for child in self.children:
            child.actual_level += amount
            child.end_level += amount
            child.update_parent_actual_liveness()
    def __str__(self):
        return "id: {}, type: {}, mode: {}, child_count: {}, parents: {}".format(self.instruction_id, self.type, self.mode, len(self.children), [node.id for node in self.parents])

class Graph:
    def __init__(self, window_size, log_address, address_dir, live_var_dir, regfile_size, alu_limit=8, avg_load_delay=0):
        self.log_address = log_address
        self.addr_file = open(address_dir, 'w') if log_address else None
        self.window_size = window_size
        self.avg_load_delay = avg_load_delay
        self.edges = {}
        self.edge_pairs = []
        self.forward_arithmetic_count = 0
        self.reverse_arithmetic_count = 0
        self.forward_important_arithmetic_count = {'mul': 0, 'div': 0, 'or': 0}
        self.reverse_important_arithmetic_count = {'mul': 0, 'div': 0, 'or': 0}
        
        self.max_forward_level = 0
        self.max_forward_actual_level = 0
        self.max_reverse_actual_level = 0
        self.max_reverse_level = 0

        self.forward_loads = 0
        self.forward_stores = 0
        self.reverse_loads = 0
        self.reverse_stores = 0
        
        self.forward_unique_address = {}
        self.reverse_unique_address = {}
        self.nodes = {}
        self.levels = {}
        self.lives_per_level = {}
        self.children_per_level = {}
        self.insts_per_level = {}
        self.level_info = {}
        self.regfile = RegisterFile(regfile_size)
        self.visited_addresses = {}
        self.alu_limit = alu_limit
        self.remaining_alues_in_level = [alu_limit]

        self.propagated_vars = get_dict_from_file(live_var_dir)
        self.cost = 0
        self.curr_id = 0

        self.f_edge_count = 0
        self.r_edge_count = 0
        self.i_edge_count = 0

        self.forward_node_count = 0
        self.reverse_node_count = 0

        self.fw_ld_set = set()
        self.fw_st_set = set()
        self.rev_ld_ld_dict = {}
        self.rev_st_ld_dict = {}
        self.rev_ld_count = 0
        self.fw_mem_op_count = 0

    @property
    def node_count(self):
        return self.forward_node_count + self.reverse_node_count

    def handle_arithmetic(self, node):
        if node.is_forward():
            self.forward_arithmetic_count += 1
            for i in self.forward_important_arithmetic_count:
                if i in node.type:
                    self.forward_important_arithmetic_count[i] += 1
                    break
        else:
            self.reverse_arithmetic_count += 1
            for i in self.reverse_important_arithmetic_count:
                if i in node.type:
                    self.reverse_important_arithmetic_count[i] += 1
                    break    
    def handle_memory_combination(self, node):
        # handling memory combination
        if node.is_forward() and node.is_load() and node.get_address() not in self.fw_st_set:
            self.fw_ld_set.add(node.get_address())
        if node.is_forward() and node.is_store():
            if node.get_address() in self.fw_ld_set:
                self.fw_ld_set.remove(node.get_address())
            self.fw_st_set.add(node.get_address())

        if node.is_reverse() and node.is_load():
            self.rev_ld_count += 1
            if node.get_address() in self.fw_st_set:
                if node.get_address() not in self.rev_st_ld_dict:
                    self.rev_st_ld_dict[node.get_address()] = 1
                else:
                    self.rev_st_ld_dict[node.get_address()] += 1
            if node.get_address() in self.fw_ld_set:
                if node.get_address() not in self.rev_ld_ld_dict:
                    self.rev_ld_ld_dict[node.get_address()] = 1
                else:
                    self.rev_ld_ld_dict[node.get_address()] += 1
    
    def handle_mem_op(self, node):
        if node.is_forward():
            self.fw_mem_op_count += 1
            if node.get_address() not in self.forward_unique_address:
                self.forward_unique_address[node.get_address()] = 1
            else:
                self.forward_unique_address[node.get_address()] += 1
        if node.is_reverse():
            if node.get_address() not in self.reverse_unique_address:
                self.reverse_unique_address[node.get_address()] = 1
            else:
                self.reverse_unique_address[node.get_address()] += 1
        
        if node.is_forward():
            if node.is_load():
                self.forward_loads += 1
            else:
                self.forward_stores += 1
        if node.is_reverse():
            if node.is_load():
                self.reverse_loads += 1
            else:
                self.reverse_stores += 1    

        self.handle_memory_combination(node)
        

    def update_max_level(self, node):
        if node.is_forward():
            if node.level > self.max_forward_level:
                self.max_forward_level = node.level
        elif node.is_reverse():
            if node.level > self.max_reverse_level:
                self.max_reverse_level = node.level

    def get_parents(self, line, node_type, node_id):
        parents = []
        for i in line.split(',')[1:-1]:
            if 'Parent' in i:
                parent_id = i.split(":")[1].strip()
                if parent_id in self.nodes:
                    parents.append(self.nodes[parent_id][-1])
                elif parent_id in self.propagated_vars:
                    if self.propagated_vars[parent_id] in self.nodes:
                        parents.append(self.nodes[self.propagated_vars[parent_id]][-1])
                    else:
                        parent_node = Node(parent_id, 0, [], "root", actual_level=self.get_next_free_level())
                        if parent_node.actual_level > self.max_forward_actual_level:
                            self.max_forward_actual_level = parent_node.actual_level
                        self.nodes[parent_id] = [parent_node]
                        parents.append(parent_node)
                else:
                    parent_node = Node(parent_id, 0, [], "root", actual_level=self.get_next_free_level())
                    if parent_node.actual_level > self.max_forward_actual_level:
                            self.max_forward_actual_level = parent_node.actual_level
                    self.nodes[parent_id] = [parent_node]
                    parents.append(parent_node)
        if node_type == 'store':
            if node_id in self.nodes:
                parents.append(self.nodes[node_id][-1])
        return parents

    def get_id(self, line):
        node_id = line.split(":")[1].split(",")[0].strip()
        return node_id if node_id not in self.propagated_vars else self.propagated_vars[node_id] # If this is an alias name
    
    def add_level(self, new_node):
        if new_node.level not in self.levels:
            self.levels[new_node.level] = []
        self.levels[new_node.level].append(new_node)
    
    def handle_write_to_file(self, new_node):
        visited = ''
        if new_node.get_address() in self.visited_addresses:
                visited = '_visited'
        self.visited_addresses[new_node.get_address()] = True
        self.addr_file.write(new_node.mode + '_' + new_node.get_address() + visited + '\n')
    
    def get_next_free_level(self):
        if self.remaining_alues_in_level[-1] > 0:
            self.remaining_alues_in_level[-1] -= 1
        else:
            self.remaining_alues_in_level.append(self.alu_limit)
        return len(self.remaining_alues_in_level) - 1  
        
    def add_node(self, line):  # line format: "Mode_Node: id, Parent: , Parent: ..., Type"
        node_id = self.get_id(line)
        
        node_type = line.split(",")[-1].strip()
        mode = line.split("_")[0]

        parents = self.get_parents(line, node_type, node_id)
        
        if not node_id in self.nodes:
            self.nodes[node_id] = []
        new_node = Node(node_id, len(self.nodes[node_id]), parents, node_type, mode, self.get_next_free_level())
        self.nodes[node_id].append(new_node)
        self.add_level(new_node)
        for i in parents:
            i.add_child(new_node)
            if i.contains_edge:
                if not i in self.edges:
                    self.edges[i] = []
                if i.is_forward() and new_node.is_reverse():
                    self.edges[i].append(new_node)
                    if new_node.is_load():
                        self.edge_pairs.append((i, new_node))

        
        if new_node.is_arithmetic():
            self.handle_arithmetic(new_node)
        if new_node.is_mem_op():
            self.handle_mem_op(new_node)
            if self.log_address:
                self.handle_write_to_file(new_node)

        self.update_max_level(new_node)
        new_node.update_parent_actual_liveness()     

        if new_node.is_forward() and new_node.actual_level > self.max_forward_actual_level:
                self.max_forward_actual_level = new_node.actual_level
        if new_node.is_reverse() and new_node.actual_level > self.max_reverse_actual_level:
                self.max_reverse_actual_level = new_node.actual_level
        if new_node.level not in self.insts_per_level:
            self.insts_per_level[new_node.level] = 1
        else:
            self.insts_per_level[new_node.level] += 1
        if new_node.is_forward():
            self.forward_node_count += 1
        else:
            self.reverse_node_count += 1
        return new_node

    def update_lives_per_level(self, node):
        for i in range(node.liveness[0], node.liveness[1] + 1):
            if i not in self.lives_per_level:
                self.lives_per_level[i] = set()
            if node.is_forward():
                self.lives_per_level[i].add(node.id)

    def calc_max_liveness(self, restrict_mode_to=None):
        for node_id in self.nodes:         
            node_vector = self.nodes[node_id]
            if restrict_mode_to is None or node_vector[-1].mode == restrict_mode_to:
                for node in node_vector:
                    start = node.level
                    end = node.level+1
                    for child in node.children:
                        if restrict_mode_to is None or child.mode == restrict_mode_to:
                            if end < child.level:
                                end = child.level
                    node.liveness = (start, end)
                    self.update_lives_per_level(node)

    def allocate_registers(self, arithmetic_only, consider_edges=True):
        # assigning nodes to different levels
        for node_id in self.nodes:
            node_vector = self.nodes[node_id]
            for node in node_vector:
                # if node.is_mem_op():
                #     break
                # if not node.is_forward():
                #     break
                # add the first live point
                if node.actual_level not in self.level_info:
                    self.level_info[node.actual_level] = LevelInfo()
                self.level_info[node.actual_level].add_new_node(node)
                for child in node.children:
                    if child.mode == node.mode or consider_edges:
                        if child.actual_level not in self.level_info:
                            self.level_info[child.actual_level] = LevelInfo()
                        self.level_info[child.actual_level].add_dead_node(node)
                        self.level_info[child.actual_level].add_new_node(node)

        # allocating regfile for the nodes
        sorted_levels = sorted(self.level_info.keys())
        for level in sorted_levels:
            if level in self.level_info:
                self.level_info[level].release_registers(self.regfile)
                self.level_info[level].assign_registers(self.regfile, level, consider_edges, self.avg_load_delay)
        count = 0
        for i in self.edges:
            if i.is_arithmetic():
                count += 1

    def calc_values_produced_per_level(self, restrict_mode_to=None):
        for node_id in self.nodes:
            node_vector = self.nodes[node_id]
            if restrict_mode_to is None or node_vector[-1].mode == restrict_mode_to:
                for node in node_vector:
                    if node.level not in self.children_per_level:
                        self.children_per_level[node.level] = 0
                    if restrict_mode_to is None:
                        self.children_per_level[node.level] += len(node.children)
                    else:
                        self.children_per_level[node.level] += len([i for i in node.children if i.mode == restrict_mode_to])
                        
    def print_lives_per_level(self, restrict_mode_to=None):
        print("--------------------------------\nLives Level\n")
        start = 0
        end_level = max(self.max_reverse_level, self.max_forward_level)
        while(True):
            sum_lives = 0
            for j in range(start, start + STEP):
                if not j in self.lives_per_level:
                    continue
                if j > end_level:
                    break
                sum_lives += len(self.lives_per_level[j])
            if sum_lives:
                print("Levels: {} - {}, AVG Lives: {}".format(start, min(start + STEP, end_level), sum_lives/(min(STEP, end_level - start) )))
            start += STEP
            if start >= end_level:
                break   
    
    def print_children_per_level(self, restrict_mode_to=None):
        print("--------------------------------\nChildren Per Level\n")
        self.calc_values_produced_per_level(restrict_mode_to)
        start = 0
        end_level = max(self.max_reverse_level, self.max_forward_level) + 1
        while(True):
            sum_children = 0
            sum_insts = 0
            for j in range(start, start + STEP):
                if j > end_level:
                    break
                if j not in self.children_per_level:
                    continue
                sum_children += self.children_per_level[j]
                sum_insts += self.insts_per_level[j]
            if sum_insts:
                print("Levels: {} - {}, AVG Children: {}, AVG Insts:{}, AVG Children per Inst: {}".format(start, min(start + STEP, end_level), float(sum_children)/min(STEP, end_level - start), float(sum_insts)/min(STEP, end_level - start), float(sum_children)/(sum_insts+1)))
            start += STEP
            if start > end_level:
                break
    
    def print_mem_ops_log(self):
        print("--------------------------------\nMem Ops Count")
        print("Forward Loads: {}".format(self.forward_loads))
        print("Forward Stores: {}".format(self.forward_stores))
        print("Reverse Loads: {}".format(self.reverse_loads))
        print("Reverse Stores: {}".format(self.reverse_stores))
        print("Total Loads: {}".format(self.forward_loads + self.reverse_loads))
        print("Total Stores: {}".format(self.forward_stores + self.reverse_stores))
        print("Total Mem Ops: {}".format(self.forward_loads + self.forward_stores + self.reverse_loads + self.reverse_stores))
    
    def log_value_count_per_cycle_count(self, restrict_mode_to=None): # Keeping n values for k cycles
        print("--------------------------------\nValue Count Per Cycle Count\n")
        live_cycles = {} 
        for node_id in self.nodes:
            node_vector = self.nodes[node_id]
            for node in node_vector:
                if not len(node.liveness):
                    continue
                cycles = node.liveness[1] - node.liveness[0]
                if cycles not in live_cycles:
                    live_cycles[cycles] = 0
                live_cycles[cycles] += 1
        if not len(live_cycles):
            return
        live_cycles = {k: v for k, v in sorted(live_cycles.items(), key=lambda item: item[1], reverse=True)}
        index = 0
        for i in live_cycles:
            index += 1
            print("Keeping {} values for {} cycles.".format(live_cycles[i], i))
            if index == 10:
                break
    
    def print_arithmetic_log(self):
        total_arithmetic_count = self.forward_arithmetic_count + self.reverse_arithmetic_count
        forward_muls = self.forward_important_arithmetic_count['mul']
        forward_divs = self.forward_important_arithmetic_count['div']
        forward_ors = self.forward_important_arithmetic_count['or']

        reverse_muls = self.reverse_important_arithmetic_count['mul']
        reverse_divs = self.reverse_important_arithmetic_count['div']
        reverse_ors = self.reverse_important_arithmetic_count['or']

        total_mul_count = forward_muls + reverse_muls
        total_div_count = forward_divs + reverse_divs
        total_or_count = forward_ors + reverse_ors
        print("--------------------------------\nArithmetic Ops")
        print("Forward unique addresses: {}, Reverse unique addresses: {}\
            \nTotal Arithmetic: {} (mul: {}, div: {}, or: {}), Forward Arithmetic: {} ({}, {}, {}), Reverse Arithmetic: {} ({}, {}, {})\
            \nMax Forward Level: {}, Max Reverse Level: {}"\
            .format(len(self.forward_unique_address), len(self.reverse_unique_address),\
                       total_arithmetic_count, total_mul_count, total_div_count, total_or_count,
                        self.forward_arithmetic_count, forward_muls, forward_divs, forward_ors,\
                        self.reverse_arithmetic_count, reverse_muls, reverse_divs, reverse_ors,  
                        self.max_forward_level, self.max_reverse_level))
    
    def get_min_register_count(self):
        edges_nodes_count = 0
        if self.max_forward_level in self.lives_per_level:
            for _ in self.lives_per_level[self.max_forward_level]:
                edges_nodes_count += 1
        else:
            print("max fwd level: ", self.max_forward_level)
            print(self.lives_per_level)
        return edges_nodes_count
    
    def get_actual_min_register_count(self):
        return max([self.level_info[i].forward_node_count for i in self.level_info])
    
    def print_actual_min_register_count(self):
        m = max([self.level_info[i].forward_node_count for i in self.level_info])
        print("Actual Min Required Registers: {}".format(m))

    def get_memory_size(self):
        mem_size = 0
        for node_id in self.nodes:
            node_vector = self.nodes[node_id]
            if len(node_vector) == 0:
                continue
            node = node_vector[0]
            if node.is_mem_op():
                mem_size += 1

        return mem_size
        
    def print_log(self, restrict_mode_to=None):
        # self.print_arithmetic_log()
        # self.print_mem_ops_log()

        # calculates the liveness for registers
        self.calc_max_liveness(restrict_mode_to)

        # self.print_lives_per_level(restrict_mode_to)
        # self.print_min_register_count()
        # self.print_children_per_level(restrict_mode_to)
        # self.log_value_count_per_cycle_count(restrict_mode_to)
        self.print_liveness_per_node()
        # self.print_max_lives_in_a_level()
        # # self.plot_liveness_scatter_plot()
        # self.plot_reg_liveness_per_level_scatter_plot()
        # self.plot_mem_liveness_per_level_scatter_plot()

        # self.plot_reg_liveness_per_level_histogram()
        # self.plot_mem_liveness_per_level_histogram()
        # self.plot_reg_liveness_per_window_scatter_plot()
        # self.plot_liveness_histogram()
        # self.print_nodes_with_max_children()
        # self.print_edge_combination()
        # self.print_node_count()
    def accept(self, visitor):
        return visitor.visit(self)

    def print_avg_lifetime(self):
        print("--------------------------------\nAvg Lifetime")
        print("Avg Lifetime: {}".format(self.get_avg_lifetime()))
    
    def get_avg_lifetime(self):
        node_count = 0
        liveness = 0
        for i in self.nodes:
            node_vector = self.nodes[i]
            for node in node_vector:
                if node.is_forward():
                    liveness += node.liveness[1] - node.liveness[0]
                    node_count += 1
        return liveness/(node_count+1)

    def print_actual_avg_lifetime(self):
        print("--------------------------------\nActual Avg Lifetime")
        print("Avg Lifetime: {}".format(self.get_actual_avg_lifetime()))

    def get_actual_avg_lifetime(self):
        node_count = 0
        liveness = 0
        for i in self.nodes:
            node_vector = self.nodes[i]
            for node in node_vector:
                if node.has_children():
                    liveness += node.end_level - node.actual_level
                node_count += 1
        print(liveness, node_count)
        return liveness/(node_count+1)

    def get_actual_avg_edge_lifetime(self):
        node_count = 0
        liveness = 0
        for i in self.edges:
            node_vector = self.edges[i]
            if node_vector[0].is_load():
                for node in node_vector:
                    if node.has_children():
                        liveness += node.children[0].actual_level - node.parents[0].actual_level
                        node_count += 1
        return liveness/(node_count+1)

    def get_working_set(self):
        address_set = set()
        for i in self.edges:
            node_vector = self.edges[i]
            if node_vector[0].is_load():
                for node in node_vector:
                    address_set.add(node.parents[0].id)
        return len(address_set)
    
    def print_live_edges_per_level(self):
        print("--------------------------------\nLive Edges Per Level")

        for i in self.edges:
            node_vector = self.edges[i]
            if node_vector[0].is_load():
                for n in node_vector:
                    if n.has_children():
                        for l in n.parents:
                            print(l)
                        p = n.parents[0]
                        print(p, p.actual_level, n.children[0].actual_level)
                # for node in node_vector:
                    

    def print_max_lives_in_a_level(self):
        # print("--------------------------------\nMax Lives")
        m = max([len(self.lives_per_level[i]) for i in self.lives_per_level])
        print("Max Lives: {}".format(m))

    def print_node_count(self):
        print("--------------------------------\nNode Count")
        print("Nodes: {}, Forward Nodes: {}, Reverse Nodes: {}".format(self.node_count, self.forward_node_count, self.reverse_node_count))

    def print_edge_combination(self):
        for n in self.nodes:
            node_list = self.nodes[n]
            for node in node_list:
                for p in node.parents:
                    if node.is_forward() and p.is_forward():
                        self.f_edge_count += 1
                    elif node.is_reverse() and p.is_reverse():
                        self.r_edge_count += 1
                    elif node.is_reverse() and p.is_forward() and not p.is_root():
                        self.i_edge_count += 1
        print("--------------------------------\nEdge Combination")
        print("Forward: {}, Reverse: {}, Intermediate: {}".format(self.f_edge_count, self.r_edge_count, self.i_edge_count))

    def print_level(self, start_range, end_range, restrict_mode_to=None):
        print("--------------------------------\nLevel info")
        for i in range(start_range, end_range):
            print("--------\nLevel {}".format(i))
            for node in self.levels[i]:
                if not restrict_mode_to or node.mode == restrict_mode_to:
                    print(node)

    def print_liveness_per_node(self):
        print("--------------------------------\nLive Nodes")
        normal_count = 0
        i_edge_count = 0
        normal_liveness = 0
        i_edge_liveness = 0
        for node_id in self.nodes:
            vec = self.nodes[node_id]
            for node in vec:
                if node.contains_edge:
                    i_edge_count += 1
                    i_edge_liveness += node.liveness[1] - node.liveness[0]

                # elif node.is_forward() and not node.is_root():
                normal_count += 1
                normal_liveness += node.liveness[1] - node.liveness[0]
        normal_count = normal_count if normal_count > 0 else 1
        i_edge_count = i_edge_count if i_edge_count > 0 else 1
        # print("Non-Edged Nodes: {}, Edged nodes: {}, Non-Edged Liveness: {}, Edged Liveness: {}".format(normal_count, i_edge_count, normal_liveness, i_edge_liveness))
        print("Average Normal Liveness: {}, Average Edged-Nodes Liveness: {}".format(normal_liveness/(normal_count), i_edge_liveness/(i_edge_count)))
    def plot_liveness_scatter_plot(self):
        x = []
        y = []
        for node_id in self.nodes:
            vec = self.nodes[node_id]
            for node in vec:
                if node.contains_edge:
                    x.append(node.uid)
                    y.append(node.liveness[1] - node.liveness[0])

        plt.plot(x, y, '.')
        plt.savefig('liveness_scatterplot.png')

    def plot_reg_liveness_per_window_scatter_plot(self):
        plt.clf() 
        x = []
        y = []
        for src in self.edges:
            edge_vec = self.edges[src]
            if len(edge_vec) > 1:
                print(f'{src.id} has {len(edge_vec)} edges!')
            for dst in edge_vec:
                x.append(src.instruction_id)
                y.append((dst.instruction_id)//self.window_size)
        
        print(len(x))
        plt.plot(x, y, '.')
        plt.xlabel('Instruction ID')
        plt.ylabel('Liveness')
        plt.savefig('reg_liveness_per_window_scatterplot.png')

    def plot_reg_liveness_per_level_scatter_plot(self):
        plt.clf() 
        x = []
        y = []
        for i in range(0, self.max_forward_level):
            if i in self.levels:
                nodes_in_level = self.levels[i]
                for node in nodes_in_level:
                    if node.contains_edge and not node.is_mem_op():
                        node.uid = Node.unique_id + 1
                        Node.unique_id += 1
                        x.append(node.uid)
                        y.append((node.liveness[1] - node.liveness[0]))
        plt.plot(x, y, '.')
        plt.xlabel('Register ID')
        plt.ylabel('Liveness')
        plt.savefig('reg_liveness_per_level_scatterplot.png')

    def plot_mem_liveness_per_level_scatter_plot(self):
        plt.clf() 
        x = []
        y = []
        for i in range(0, self.max_forward_level):
            if i in self.levels:
                nodes_in_level = self.levels[i]
                for node in nodes_in_level:
                    if node.contains_edge and (node.is_mem_op() or node.is_arg()):
                        node.uid = Node.unique_id + 1
                        Node.unique_id += 1
                        x.append(node.uid)
                        y.append(node.liveness[1] - node.liveness[0])
        plt.plot(x, y, '.')
        plt.xlabel('Node UID')
        plt.ylabel('Liveness')
        plt.savefig('mem_liveness_per_level_scatterplot.png')

    def plot_reg_liveness_per_level_histogram(self):
        plt.clf() 
        hist = {}
        for i in range(0, self.max_forward_level):
            if i in self.levels:
                nodes_in_level = self.levels[i]
                count = 0
                for node in nodes_in_level:
                    if node.contains_edge and not node.is_mem_op():
                        count += 1 
                hist[i] = count
        plt.bar(hist.keys(), hist.values())
        plt.xlabel('level')
        plt.ylabel('live count')
        plt.savefig('reg_liveness_per_level_histogram.png')
    
    def plot_mem_liveness_per_level_histogram(self):
        plt.clf() 
        hist = {}
        for i in range(0, self.max_forward_level):
            if i in self.levels:
                nodes_in_level = self.levels[i]
                count = 0
                for node in nodes_in_level:
                    if node.contains_edge and (node.is_mem_op() or node.is_arg()):
                        count += 1 
                hist[i] = count
        plt.bar(hist.keys(), hist.values())
        plt.xlabel('level')
        plt.ylabel('live count')
        plt.savefig('mem_liveness_per_level_histogram.png')

    def plot_liveness_histogram(self):
        plt.clf() 
        x = []
        y = []
        for node_id in self.nodes:
            vec = self.nodes[node_id]
            for node in vec:
                if node.contains_edge:
                    x.append(node.uid)
                    y.append(node.liveness[1] - node.liveness[0])

        plt.hist(y, 20)
        plt.savefig('liveness_histogram.png')
    
    def print_nodes_with_max_children(self):
        print("--------------------------------\nMax Children")

        forward_child_count_map = {}
        reverse_child_count_map = {}

        for node_id in self.nodes:
            vec = self.nodes[node_id]
            for node in vec:
                if node.is_forward() and node.is_arithmetic():
                    if len(node.children) in forward_child_count_map:
                        forward_child_count_map[len(node.children)].append(node)
                    else:
                        forward_child_count_map[len(node.children)] = [node]
                elif node.is_reverse() and node.is_arithmetic():
                    if len(node.children) in reverse_child_count_map:
                        reverse_child_count_map[len(node.children)].append(node)
                    else:
                        reverse_child_count_map[len(node.children)] = [node]
        for i in sorted(forward_child_count_map.keys(), reverse=True):
            if i > 2:
                print("Forward nodes with {} children:".format(i))
                for node in forward_child_count_map[i]:
                    print(node.id)
        
        for i in sorted(reverse_child_count_map.keys(), reverse=True):
            if i > 2:
                print("Reverse nodes with {} children:".format(i))
                for node in reverse_child_count_map[i]:
                    print(node.id)
    
    def get_instructions(self):
        instructions = {}
        for node_id in self.nodes:
            vec = self.nodes[node_id]
            for node in vec:
                if node.parents and node.children:
                    instructions[node.instruction_id] = node.to_inst()
        return instructions

    def get_mem_op_combination(self):
        if self.rev_ld_count == 0:
            return 0, 0, 0
        ld_ld = sum(i for i in self.rev_ld_ld_dict.values())/self.rev_ld_count
        st_ld = sum(i for i in self.rev_st_ld_dict.values())/self.rev_ld_count
        return ld_ld, st_ld, self.rev_ld_count/self.fw_mem_op_count 