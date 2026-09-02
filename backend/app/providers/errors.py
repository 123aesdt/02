class ProviderError(Exception):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass
