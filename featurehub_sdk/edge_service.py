class EdgeService:
    async def poll(self):
        pass

    def client_evaluated(self):
        pass

    def close(self):
        pass

    async def context_change(self, header: str):
        pass

    def cancel_poll(self):
        pass
