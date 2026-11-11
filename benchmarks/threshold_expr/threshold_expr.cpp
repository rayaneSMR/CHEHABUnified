// One program of the near-threshold dataset (RL/fhe_rl/datasets/threshold_benchmarks.txt),
// compiled by CHEHAB like the other benchmarks, for the real compile + SEAL execution
// evaluation (scripts/run_benchmarks_unified.py, benchmark "threshold").
//
// The dataset stores each program as a VecLang expression "(Vec e1 ... ek):name", with
// ciphertext variables v1..vN and the operators +, - (binary and unary) and *. Each element
// e_i becomes one scalar output out_i, in order, so the vectorizer sees (Vec e1 ... ek) again.
// The inputs get fixed random values (seeded by the line number) and the expected outputs
// (mod the plain modulus) are written to fhe_io_example.txt, so the decrypted results can be
// checked.
//
//   ./threshold_expr VECTORIZE LINE FRAMEWORK OPT_METHOD WINDOW QUANTIFIER CSE CONST_FOLD BACKEND W_OPS
//
// Same arguments as dot_product, with the slot count replaced by the (1-based) dataset line.
// The dataset is read from ./threshold_benchmarks.txt (copied there by the runner).
#include "fheco/fheco.hpp"

using namespace std;
using namespace fheco;
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <memory>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
#include "../global_variables.hpp"

namespace
{
const int64_t PLAIN_MODULUS = 786433;   // PlainModulus::Batching(16384, 20) in the generated programs

struct Node
{
  string op;                    // "+", "-", "*", or "" for a variable
  string var;
  vector<unique_ptr<Node>> args;
};

vector<string> tokenize(const string &s)
{
  vector<string> tokens;
  string cur;
  for (char c : s)
  {
    if (c == '(' || c == ')' || isspace(static_cast<unsigned char>(c)))
    {
      if (!cur.empty())
      {
        tokens.push_back(cur);
        cur.clear();
      }
      if (c == '(' || c == ')')
        tokens.push_back(string(1, c));
    }
    else
      cur += c;
  }
  if (!cur.empty())
    tokens.push_back(cur);
  return tokens;
}

unique_ptr<Node> parse(const vector<string> &t, size_t &i)
{
  if (i >= t.size())
    throw invalid_argument("unexpected end of expression");
  auto node = make_unique<Node>();
  if (t[i] != "(")
  {
    if (t[i] == ")")
      throw invalid_argument("unexpected ')'");
    if (t[i].empty() || t[i][0] != 'v')
      throw invalid_argument("unsupported leaf (only variables v<i>): " + t[i]);
    node->var = t[i++];
    return node;
  }
  ++i;   // (
  node->op = t[i++];
  if (node->op != "+" && node->op != "-" && node->op != "*")
    throw invalid_argument("unsupported operator: " + node->op);
  while (i < t.size() && t[i] != ")")
    node->args.push_back(parse(t, i));
  if (i >= t.size())
    throw invalid_argument("missing ')'");
  ++i;   // )
  size_t n = node->args.size();
  if (!(n == 2 || (n == 1 && node->op == "-")))
    throw invalid_argument("bad arity for operator " + node->op);
  return node;
}

int64_t mod_t(int64_t x)
{
  x %= PLAIN_MODULUS;
  return x < 0 ? x + PLAIN_MODULUS : x;
}

struct Builder
{
  unordered_map<string, Ciphertext> ciphers;
  unordered_map<string, int64_t> values;
  vector<string> order;   // variables in order of first appearance
  mt19937 rng;

  explicit Builder(unsigned seed) : rng(seed) {}

  Ciphertext var(const string &name)
  {
    auto it = ciphers.find(name);
    if (it != ciphers.end())
      return it->second;
    uniform_int_distribution<int> dist(0, 15);
    values[name] = dist(rng);
    order.push_back(name);
    return ciphers.emplace(name, Ciphertext(name)).first->second;
  }

  // Builds the DSL expression and returns its expected value mod t.
  Ciphertext build(const Node &n, int64_t &val)
  {
    if (n.op.empty())
    {
      Ciphertext c = var(n.var);
      val = values[n.var];
      return c;
    }
    if (n.args.size() == 1)
    {
      int64_t a;
      Ciphertext ca = build(*n.args[0], a);
      val = mod_t(-a);
      return -ca;
    }
    int64_t a, b;
    Ciphertext ca = build(*n.args[0], a);
    Ciphertext cb = build(*n.args[1], b);
    if (n.op == "+")
    {
      val = mod_t(a + b);
      return ca + cb;
    }
    if (n.op == "-")
    {
      val = mod_t(a - b);
      return ca - cb;
    }
    val = mod_t(a * b);
    return ca * cb;
  }
};

string read_dataset_line(int line)
{
  ifstream in("threshold_benchmarks.txt");
  if (!in)
    throw invalid_argument("cannot open threshold_benchmarks.txt");
  string s;
  for (int i = 1; getline(in, s); ++i)
    if (i == line)
    {
      auto colon = s.rfind(':');   // "(Vec ...):name"
      return colon == string::npos ? s : s.substr(0, colon);
    }
  throw invalid_argument("dataset line " + to_string(line) + " not found");
}

void fhe(int line)
{
  vector<string> t = tokenize(read_dataset_line(line));
  if (t.size() < 3 || t[0] != "(" || t[1] != "Vec")
    throw invalid_argument("expected (Vec ...)");
  size_t i = 2;
  vector<unique_ptr<Node>> elems;
  while (i < t.size() && t[i] != ")")
    elems.push_back(parse(t, i));
  if (elems.empty())
    throw invalid_argument("empty Vec");

  Builder b(1000u + static_cast<unsigned>(line));
  vector<int64_t> expected;
  for (size_t k = 0; k < elems.size(); ++k)
  {
    int64_t v;
    Ciphertext c = b.build(*elems[k], v);
    c.set_output("out" + to_string(k));
    expected.push_back(v);
  }

  // Inputs "<name> <is_cipher> <is_signed> <value>", outputs "<name> <is_cipher> <value>"
  ofstream io("fhe_io_example.txt");
  io << "1 " << b.order.size() << " " << expected.size() << "\n";
  for (const auto &name : b.order)
    io << name << " 1 1 " << b.values[name] << "\n";
  for (size_t k = 0; k < expected.size(); ++k)
    io << "out" << k << " 1 " << expected[k] << "\n";
}
} // namespace

int main(int argc, char **argv)
{
  bool vectorize_code = argc > 1 ? stoi(argv[1]) : true;
  int line = argc > 2 ? stoi(argv[2]) : 1;
  string framework = argc > 3 ? argv[3] : "constrained";
  int optimization_method = argc > 4 ? stoi(argv[4]) : 0;   // 0 = egraph, 1 = RL
  int window = argc > 5 ? stoi(argv[5]) : 0;
  bool call_quantifier = argc > 6 ? stoi(argv[6]) : true;
  bool cse = argc > 7 ? stoi(argv[7]) : true;
  bool const_folding = argc > 8 ? stoi(argv[8]) : true;
  int backend = argc > 9 ? stoi(argv[9]) : 0;
  float w_ops = argc > 10 ? stof(argv[10]) : 0.5f;
  if (w_ops < 0.0f || w_ops > 1.0f)
  {
    cerr << "Error: w_ops must be between 0 and 1" << endl;
    return 1;
  }
  float w_keys = 1.0f - w_ops;
  if (backend != 0 || !vectorize_code)
  {
    cerr << "threshold_expr supports only the vectorized SEAL path (VECTORIZE=1, BACKEND=0)" << endl;
    return 1;
  }

  if (cse)
  {
    Compiler::enable_cse();
    Compiler::enable_order_operands();
  }
  else
  {
    Compiler::disable_cse();
    Compiler::disable_order_operands();
  }
  if (const_folding)
    Compiler::enable_const_folding();
  else
    Compiler::disable_const_folding();

  auto t = chrono::high_resolution_clock::now();
  string func_name = "fhe";
  const auto &func = Compiler::create_func(func_name, 1, 20, false, true);
  fhe(line);
  string gen_name = "_gen_he_" + func_name;
  string gen_path = "he/" + gen_name;
  ofstream header_os(gen_path + ".hpp");
  if (!header_os)
    throw logic_error("failed to create header file");
  ofstream source_os(gen_path + ".cpp");
  if (!source_os)
    throw logic_error("failed to create source file");
  cout << " window is " << window << endl;
  if (VECTORIZATION_ENABLED)
    Compiler::gen_vectorized_code(func, window, optimization_method, w_ops, w_keys, framework);
  if (SIMPLIFICATION_ENABLED)
    Compiler::compile(func, Compiler::Ruleset::depth, trs::RewriteHeuristic::bottom_up);
  Compiler::gen_he_code(func, header_os, gen_name + ".hpp", source_os);
  cout << "Generated SEAL code: " << gen_path << ".hpp/.cpp" << endl;
  chrono::duration<double, milli> elapsed = chrono::high_resolution_clock::now() - t;
  cout << elapsed.count() << " ms\n";
  if (call_quantifier)
  {
    util::Quantifier quantifier{func};
    quantifier.run_all_analysis();
    quantifier.print_info(cout);
  }
  return 0;
}
