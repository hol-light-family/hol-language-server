(* Loads lib/util.ml with `needs`, then ctx.ml with `loadt`. ctx.ml uses
   ADD_SYM_ALT from util.ml without loading util.ml itself. *)

needs "lib/util.ml";;
loadt "ctx.ml";;
