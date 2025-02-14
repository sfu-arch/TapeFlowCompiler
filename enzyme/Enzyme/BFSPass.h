
#ifndef BFS_H
#define BFS_H

#include <fstream>
#include <iostream>
#include <map>
#include <set>

#include "llvm/IR/DataLayout.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/InstVisitor.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/Pass.h"
#include "llvm/Support/raw_ostream.h"

using namespace llvm;

namespace instrumem {
bool isValidInstruction(Instruction *inst);
std::vector<std::pair<Value *, int>> SortMap(std::map<Value *, int> &map);

class Node {
public:
  Node(Value *v) : value(v), level(0), cost(0) {
    if (isa<Instruction>(v) && (isa<LoadInst>(v) || isa<StoreInst>(v)))
      is_memop = true;
  }
  Value *GetValue() { return value; }

  void AddChild(Node *child);

  int GetInstructionCost(Value *inst);
  int GetFifoSize(int max_level);
  int GetChildrenCount() { return children.size(); }
  int GetFifoSizeBetweenNodes(int max_level, int parent_level, int child_level);

  bool IsMemOp() { return is_memop; }

  void PushToTape();
  void UndoPushToTape(int prev_cost);
  void AssignChildCost();
  void PropagateCost(int parent_old_cost, int parent_new_cost);

  void DumpForward(std::ofstream &myfile);
  void DumpReverse(std::ofstream &myfile);
  void DumpRecompute(std::ofstream &myfile, int);
  void DumpStore(std::ofstream &myfile);

  std::string RecurseToRoot(std::string prefix);
  std::string GetNodeName();

  bool visited = false;
  int level;
  int cost;

private:
  Value *value;
  bool is_memop = false;

  std::set<Node *> children;
  std::set<Node *> parents;
};

class Graph {
public:
  Graph() {}

  void AddNode(Value *v) { nodes[v] = new Node(v); }
  Node *operator[](Value *v) { return nodes[v]; }

  std::map<Value *, Node *> operator()() { return nodes; }
  std::map<Value *, int> GetLevels();

  int GetTotalCost();
  int GetFifoSize();
  int GetMaxLevel();
  int GetParentChildCount();

  bool contains(Value *v) { return nodes.find(v) != nodes.end(); }

  void DumpForward(std::ofstream &myfile);
  void DumpReverse(std::ofstream &myfile);
  void DumpRecompute(std::ofstream &myfile);
  void DumpStore(std::ofstream &myfile);

  void PrintLevels();

private:
  std::map<Value *, Node *> nodes;
};

struct BFSPass : public llvm::FunctionPass, llvm::InstVisitor<BFSPass> {
public:
  static char ID;
  BFSPass();
  bool runOnFunction(llvm::Function &f) override;
  void visitInstruction(Instruction &I);

  std::ofstream myfile;

private:
  std::map<llvm::Value *, std::vector<llvm::Value *>> args;
  Graph g;
};

} // namespace instrumem

#endif
