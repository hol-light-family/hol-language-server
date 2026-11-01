(* Words in comments and strings are text, not uses of a name.
   Checked: Go to Definition and hover find the name in code, and nothing in a
   comment, a string, or an import that is not code. *)

needs "lib/util.ml";;

let lookup_target = 1;;
let real_use = lookup_target;;
(* goto: real_use = lookup_target +11 => let lookup_target +4 *)

(* prose lookup_target here *)
(* goto: prose lookup_target +6 => nowhere *)
(* hover: prose lookup_target +6 => none *)

(* first line
   multiline lookup_target here *)
(* goto: multiline lookup_target +10 => nowhere *)
(* hover: multiline lookup_target +10 => none *)

(* outer (* inner *) after_nested lookup_target here *)
(* goto: after_nested lookup_target +13 => nowhere *)
(* hover: after_nested lookup_target +13 => none *)

let s1 = "plain lookup_target here";;
(* goto: plain lookup_target +6 => nowhere *)
(* hover: plain lookup_target +6 => none *)

let s2 = "first line
  spanning lookup_target here";;
(* goto: spanning lookup_target +9 => nowhere *)
(* hover: spanning lookup_target +9 => none *)

let s4 = {|quoted lookup_target here|};;
(* goto: quoted lookup_target +7 => nowhere *)
(* hover: quoted lookup_target +7 => none *)

let s5 = {id|first line |} still inside
  tagged lookup_target here|id};;
(* goto: tagged lookup_target +7 => nowhere *)
(* hover: tagged lookup_target +7 => none *)

(* A quote in it must not start an ordinary string, which would hide the local name after it. *)
let scoped_fn param = let s6 = {|it"s|} in let inner_name = param in inner_name;;
(* goto: in inner_name +3 => let inner_name +4 *)

(* commented needs "lib/util.ml" here *)
(* goto: commented needs "lib/util.ml +17 => nowhere *)

let s3 = "text needs \"lib/util.ml\" here";;
(* goto: text needs \"lib/util.ml +13 => nowhere *)

let t1 = `in_term needs "lib/util.ml" here`;;
(* goto: in_term needs "lib/util.ml +15 => nowhere *)

let after_all = lookup_target;;
(* goto: after_all = lookup_target +12 => let lookup_target +4 *)
