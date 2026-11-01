(* An open in a loaded file can rely on an open in a file loaded before it.
   Checked: treasure resolves through both, whatever the iteration order of a set. *)

needs "provider.ml";;
needs "consumer.ml";;

let use = treasure;;
(* goto: use = treasure +6 => let treasure +4 @open_order/provider.ml *)
