(* The file opening Inner loads before the file opening M, so Inner names nothing.
   Checked: treasure does not resolve, though both opens are in the loaded files. *)

needs "late_consumer.ml";;
needs "provider.ml";;

let use = treasure;;
(* goto: use = treasure +6 => nowhere *)
