set pagination off
set breakpoint pending on
break ggml_gemm_q4_K_8x4_q8_K
commands
silent
printf "E28_DISPATCH e23-superseded symbol=ggml_gemm_q4_K_8x4_q8_K n=%d nr=%d nc=%d\n", n, nr, nc
bt 4
quit
end
run
