(* The same two files as before_provider.ml, in the other order.
   Checked: treasure resolves. *)

needs "provider.ml";;
needs "late_consumer.ml";;

let use = treasure;;
(* goto: use = treasure +6 => let treasure +4 @open_order/provider.ml *)
