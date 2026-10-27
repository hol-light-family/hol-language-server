(* Parser cases for top-level definitions.
   Checked: the definitions in the `expect` comments, and 1 load.
   - Destructuring patterns: lists, arrays, conses, tuples.
   - Labeled and optional arguments, and type annotations.
   - Operator names in parentheses, such as (THEN1).
   - Nested comments, and comments between arguments.
   - Statements cut short (`let x = ;;`).
   - `needs "modules.ml"`: followed when the file is indexed. *)

let [a; b] = [1; 2];;
(* expect: a b *)
let [|a; b; c;|] = ;;
(* expect: a b c *)
let x :: _ = ;;
(* expect: x *)
let x, y :: z :: [u;], v = ;;
(* expect: x y z u v *)
let f ~x ?(y: int) z ~(zz) ~(zz: float): int = 2;;
(* expect: f *)

(* Examples from core HOL Light files *)
let compare (Set m1, Set m2) = Pmap.compare compareValue (m1,m2);;
(* expect: compare *)

(* Nested (* comments 
*) *)

needs "modules.ml";;

let idSetAddMax max ((_,len) as id_len, set) : idSet =
  if len <= max then Pset.add set id_len else set;;
(* expect: idSetAddMax *)

let augment(Prover(_,aug)) thms = aug thms;;
(* expect: augment *)

let scrub_const (Rws htbl) c =
  let name, _ = dest_const c in
  Hashtbl.remove htbl name;;
(* expect: scrub_const *)

let set_skip_name (Rws htbl as rws) p sk =
  let { contents = db, _ } as rl = assoc_clause rws p in
  rl := db, sk;;
(* expect: set_skip_name *)

let inst_rw (th, monitoring, {rule = Rw {thm = thm; rhs = rhs;}; inst = (bds, tysub)}) =
  let tirhs = inst_type_dterm (tysub, rhs);;
(* expect: inst_rw *)

let nodeSize ({size = x}) = x;;
(* expect: nodeSize *)

let key_of (Rw {cst = cst; lhs = lhs}) =
  let name, _ = dest_const cst in
  (name, length lhs, cst);;
(* expect: key_of *)

let freshVars (Clause {parameters=parameters;id=id;thm=thm;_;}) =
    Clause {parameters = parameters; id = id; thm = Rule.freshVars thm};;
(* expect: freshVars *)

let (THEN1),(THENL1) =
  let propagate_empty i [] = [];;
(* expect: THEN1 THENL1 *)

let ((THEN_TCL1): thm_tactical -> thm_tactical -> thm_tactical) =
  fun ttcl1 ttcl2 ttac -> ttcl1 (ttcl2 ttac);;
(* expect: THEN_TCL1 *)
  
let (STRIP_TAC1: tactic) =
    fun g ->
      try STRIP_GOAL_THEN STRIP_ASSUME_TAC g
      with Failure _ -> failwith "STRIP_TAC";;
(* expect: STRIP_TAC1 *)

let (UNDISCH_THEN1:term->thm_tactic->tactic) =
  fun tm ttac (asl,w) ->
    let thp,asl' = remove (fun (_,th) -> aconv (concl th) tm) asl in
    ttac (snd thp) (asl',w);;
(* expect: UNDISCH_THEN1 *)

let FIRST_X_ASSUM1 ttac =;;
(* expect: FIRST_X_ASSUM1 *)

let (CHEAT_TAC1:tactic) =
  fun (asl,w) -> ACCEPT_TAC(mk_thm([],w)) (asl,w);;
(* expect: CHEAT_TAC1 *)

let equals_goal1 ((a,w):goal) ((a',w'):goal) =
  forall2 (fun (s,th) (s',th') -> s = s' && equals_thm th th') a a' && w = w';;
(* expect: equals_goal1 *)

let equals_goal2 ((*first arg *)(a,w):goal) ((*second (*arg*)*)(a',(*between*)w'):goal): (* return type *) bool =
  forall2 (fun (s,th) (s',th') -> s = s' && equals_thm th th') a a' && w = w';;
(* expect: equals_goal2 *)


let PART_MATCH,GEN_PART_MATCH =
    let rec match_bvs t1 t2 acc =;;
(* expect: PART_MATCH GEN_PART_MATCH *)

(* Other examples *)
let TEST_TAC (x: int) : tactic = x;;
(* expect: TEST_TAC *)
    
let in_ball_annulus = prove(`!v. v IN ball_annulus <=> &2 <= norm v /\ norm v <= &2 * h0 /\ ~(v = vec 0)`,ALL_TAC);;
(* expect: in_ball_annulus:theorem *)

(* Test definitions from s2n-bignum *)

let ARM_MK_EXEC_RULE th0: thm * (thm option array) = 
  let th0 = INST [`pc':num`,`pc:num`] (SPEC_ALL th0);;
(* expect: ARM_MK_EXEC_RULE *)

let mk_sublist_of_mc (new_mc_name:string) (mc_th:thm)
    (ofs_and_len:term*term) (mc_length_th:thm): thm * thm * (thm * thm option array) = 1;;
(* expect: mk_sublist_of_mc *)
