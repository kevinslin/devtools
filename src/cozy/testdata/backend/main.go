package main

import (
	"flag"
	"fmt"
	"net/http"
	"os"
)

func main() {
	host := flag.String("host", "", "loopback host assigned to the backend")
	requestedPort := flag.String("port", "", "port assigned by Cozy")
	noOpen := flag.Bool("no-open", false, "do not open the backend in a browser")
	flag.Parse()

	port := os.Getenv("PORT")
	if port == "" || port != os.Getenv("COZY_PORT") {
		fmt.Fprintln(os.Stderr, "PORT and COZY_PORT must contain the same port")
		os.Exit(2)
	}
	if *host != "127.0.0.1" || *requestedPort != port || !*noOpen {
		fmt.Fprintln(os.Stderr, "backend must receive --host 127.0.0.1, the assigned --port, and --no-open")
		os.Exit(2)
	}

	fmt.Println("cozy test backend ready")
	if err := http.ListenAndServe("127.0.0.1:"+port, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, "cozy backend: %s", r.Host)
	})); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
