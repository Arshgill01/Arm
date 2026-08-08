set pagination off
set breakpoint pending on
break ggml_gemv_q6_K_8x8_q8_K
commands
silent
printf "E28_DISPATCH e24 symbol=ggml_gemv_q6_K_8x8_q8_K n=%d nc=%d\n", n, nc
bt 4
quit
end
run
